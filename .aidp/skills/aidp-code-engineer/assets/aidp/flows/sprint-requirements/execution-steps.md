# sprint-requirements · 执行步骤详情（Step 0–3）

> 本文件是 `/sprint-requirements` 命令 **执行步骤（Step 0 输入扫描 → Step 1 调 ux-logic-extractor → Step 1.5 命令级后处理 → Step 2 补充元数据 → Step 3 更新状态）** 的完整详细步骤，由命令主体（`.aidp/commands/sprint-requirements.md`）在**进入「执行步骤」时用 Read 工具按需加载**。命令主体只保留「执行步骤」的**骨架表 + 关键规则 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入执行步骤后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤（Step 1.5 的 (a)~(e) 后处理尤其易漏）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-requirements/execution-steps.md`。理据/根因见同目录 `rationale.md`。

---

## 执行步骤

### Step 0：输入扫描与多系统检测

**Step 0.1 扫描产品 PRD**

```bash
ls docs/requirements/{version}/产品提供/**/*.md   # 优先源
ls docs/requirements/PRD-*.md                    # 仅当上面为空时使用
```

记录所有命中的文件路径，作为本命令的输入清单。

**Step 0.2 多系统智能判断**

读取所有 PRD 内容，根据以下信号判断是否涉及多个系统：
- 文档标题/章节中出现 "XX 系统 / YY 平台 / ZZ 模块" 等并列且互不依赖的子系统
- 不同 PRD 描述的目标用户群、业务域明显不同
- 单一 PRD 内部出现 "本期建设包含 N 个子系统" 类陈述

**判断结果**：
- `single`：单一系统（默认）→ 后续输出 `00_索引.md` + `01_研发需求.md`（约定 15）
- `multi`：多系统 → 后续按系统拆分，输出 `00_索引.md` + `0N_系统名.md`
- `unsure`：边界不清 → 向用户列出候选系统清单 + 提议拆分方案，等用户裁决

### Step 1：调用 ux-logic-extractor skill（模式由 SKILL 按输入自判；本场景含 PRD 通常走融合增强 B，缺 PRD 时 SKILL 自降级 A）

使用 `Skill` 工具调用 `ux-logic-extractor`，由 skill 自主完成 PRD 生成 + 多维度（详见 SKILL.md）独立 Agent 检查 + 多轮 Quality Review 阻塞完成判定。**SKILL 内规则为单一信源**（含职责边界 / 上游引用规则 / 拆分数量控制 / 不中断原则 / 不臆造兜底 / 数据闭环完整性 / 复用优先维度等），命令端按 CLAUDE.md 约定 21 不复述、不修改，仅做编排和项目级补充。

> 详细规则查 `.aidp/skills/ux-logic-extractor/SKILL.md`；命令端只负责传参 + 接收输出 + 下方 Step 1.5 的 AIDP 编排后处理。

**调用参数**（按 skill 当前接口）：
- **产品需求文档**：Step 0.1 扫描到的全部 PRD 路径
- **HTML 原型**：`docs/prototype/{version}/code/`（如存在）
- **★ 原型内容基线**：`docs/design/detail/{version}/*原型内容基线.md`（**存在则必传** — SKILL 输入表标「有则强制消费」，作原型覆盖度基准；不存在则不传，SKILL 自动回退到从原型 `code/` 现场逐页清点。首版规划期通常尚未产出〔由 `/sprint-design` Step 0.7 产出〕，**重跑 / 补充模式 / 跨版本继承**时常已存在）
- **★ 设计令牌 / 原型 manifest**：`docs/design/detail/{version}/*设计令牌.md` + 原型目录内 `DESIGN-MANIFEST.json` / `DESIGN-HANDOFF.md`（**存在则传**，SKILL 标「有则读取」；不存在跳过，不臆造）
- **其它参考文件**（可选）：`memory/productContext.md`、`memory/projectBrief.md`

**输出路径约定**（命令端通过 prompt 显式告诉 skill，覆盖 skill 默认 `docs/product/{项目名}/`）：
- **目标目录**：`docs/requirements/{version}/研发需求/`
- **专职索引名**：`00_索引.md`（**SKILL 原生产出的专职索引**，恒有；记文件清单 + 生成时间 + 主/补充标识，约定 15）
- **单文件内容主文档名**：`01_研发需求.md`（内容主文档从 `01_` 起，约定 14/15。**SKILL 原生产出 `01_PRD-{项目名}.md`**，命令端仅把内容主文档名**映射**为 `01_研发需求.md`）
- **子文档命名**：`01_<业务域>.md` / `02_<业务域>.md` / ...（skill 自带 约定 15 兼容编号；中文自描述）

> **项目级补充（不属于 SKILL 范畴，命令端负责）**：
> - 多系统拆分（不同于 SKILL 的"业务域拆分"）+ 头部元数据表 在 Step 1.5 后处理，**不传给 skill**
> - 命令端 Step 1.5(e) 做 AIDP 硬规范回检（路径前缀 / 索引文件存在性等）+ 按 P0/P1/P2 输出汇总给用户
> - 其他 SKILL 内置行为（模式 B 融合增强 / 差异标注 / 不中断原则 / Q-NNN 编号 / 不臆造兜底维度等）查 SKILL.md。

**★ 项目级补充 — 信号传递（精简，按约定 21）**：

> 设计意图见同目录 `rationale.md`。

```
【项目级 prompt 增强 — 信号传递】

本次调用是 /version 串联场景，**上游来源齐全**：
- 产品 PRD：docs/requirements/{version}/产品提供/*.md（必读，Step 0.1 已扫描）
- 原型代码：docs/prototype/{version}/code/（必读，含 .jsx/.vue/.html 等）
- 高保真原型：docs/prototype/{version}/mockup/（如存在则必读）

【信号】上游齐全 → 请走严格模式（不走"独立使用上游不全时"的宽松判定）。

SKILL 内置规则单一信源（命令端按约定 21 不复述，不写死行数/阈值）：REQ 段头部上游溯源 + 引用密度覆盖率，均由 SKILL 内置硬核回检 + 脚本 `.aidp/skills/ux-logic-extractor/scripts/check_req_upstream.py` 把关（具体头部行数 / 覆盖率阈值详见 SKILL.md）。
```

命令端把上述 prompt 作为「调用约束」原样追加到 SKILL 调用的 system prompt 末尾。SKILL QR 通过后，命令端在 Step 1.5 末尾再用 bash grep 兜底核验（详见 Step 1.5e 兜底回检）。

### Step 1.5：命令级后处理（AIDP 编排责任）

接收 skill 返回的融合 PRD 内容后，命令端按 AIDP 约定做以下后处理（(a)~(e)）：

**(a) 多系统判定 + 拆分**（按 Step 0.2 的 single/multi/unsure）：
- `single` → 整段写入 `docs/requirements/{version}/研发需求/01_研发需求.md`（并生成 `00_索引.md`）
- `multi`  → 切分为 `01_<系统>.md` / `02_<系统>.md` + `00_索引.md`（含系统清单与各分册范围）
- `unsure` → 暂停，列候选系统 + 提议方案，待用户裁决

> ★ **归一边界**：`00_索引.md` + `01_` 序号态由上游 SKILL 原生产出；`/version` 串联场景下最终由其 Step 2.4.4 统一幂等归一/校验，本命令**单独调用**时在此就地生成兜底（幂等，已合规则不动）。

**(b) 多 PRD 冲突识别**（仅当输入 ≥2 份产品 PRD）：
- 对同一概念在不同 PRD 间不一致的描述，写入头部「⚠️ 冲突项与解决方案」表（来源 / 冲突 / 采用方案 / 理由）

**(c) 不清晰需求标注 — 不中断原则**：
- skill 内部已按「⚠️ 不中断原则(Critical)」处理：所有"文档与原型不一致 / 原型未体现 / 描述模糊 / 缺验收标准 / 缺异常分支"等问题**不中断**，就地标 `❓ 待澄清` + `🔧 Agent 暂行方案`，集中汇总到 PRD 末尾「十、待澄清问题清单」（多文件 `99_待澄清问题清单.md`），编号 `Q-NNN`
- 命令端不因待澄清而暂停 /sprint-design 的具体行为（展示汇总 / P0≥3 提示 / /sprint-bugfix 修订路径）权威表述见下方「Q-NNN 优先级汇总」段，本处不复述

**(d) 过度内容裁剪**：
- ⛔ **裁剪必须三步齐做，缺一即静默丢弃**（(d) 发生在 SKILL 产出表 D 之后，不回改表 D 则被裁条目
  在表 D 里仍标"已承接" → `check_prd_item_coverage` 判 100% 通过 → 零告警；而「✂️ 已裁剪」表
  **不是**待澄清清单，auditor C-4 也看不见它）：
  ① 回写「PRD 条目映射表」（表 D）该行处置为 **`本版不做`**；
  ② 在「十、待澄清问题清单」登记 `Q-ITEM-NNN`（含 🔧 Agent 暂行方案 + 待产品确认列）；
  ③ 重跑 `check_prd_item_coverage.py` 确认无"未分类"残留。
- 超出本版目标 / 与里程碑无关的需求 → 写入头部「✂️ 已裁剪」表（来源 / 裁剪内容 / 理由），**不**进主体

**(e) ★ SKILL 脚本复核（职责边界 / 字段清单 / PRD 条目反向覆盖 / 表 E·F / 第三方对接 / 拆分命名）**：

> **单一信源 = `.aidp/skills/ux-logic-extractor/references/flow-qr-dispatch.md`**（脚本清单、触发条件、退出码、`98_语义变更与需求作废.json` 机读副本产出与 rc 处置全部在那里，由其质量检查子 Agent 步骤 0 强制跑）；命令端**不另列脚本、不复述判级**。
>
> 需要复核时（SKILL 报告缺脚本退出码证据 / 产物明显违规）→ **派独立子 Agent 按该文件原样跑全部脚本**（`<SKILL_DIR>` = `.aidp/skills/ux-logic-extractor`，PRD 目录 = `docs/requirements/{version}/研发需求/`，`check_prd_item_coverage.py` 的 `--prd-source` = `docs/requirements/{version}/产品提供/`），只回传各脚本退出码 + 摘要；⛔ 不在主对话内联跑。判违规 → 暂停 Step 2 让 SKILL 重写；退出码 `2` = 入参错，修参数重跑、不算违规；`98_语义变更与需求作废.json` 未落盘按 SKILL 口径阻断（它是 version-auditor 审计 H 的唯一机读信源）。SKILL QR 标记通过但产物明显违规 → 在模板仓库修 SKILL（约定 16），不在此步绕过。

**Q-NNN 优先级汇总**（命令端读取十章节后按 P0/P1/P2 分组，在终端输出给用户）：

```
📋 待澄清问题清单汇总
   P0（建议先人工裁决）: Q-002 状态机可逆性 / Q-003 用户状态种类
   P1（影响重要分支）  : Q-001 默认排序规则
   P2（边缘场景）      : Q-004 头像必填性

   💡 用户可在并行 /sprint-design 时确认 Q-NNN；用户裁决与 Agent 暂行方案不一致时，由 /sprint-bugfix 累进 Sprint 修订
```

> **不中断原则 — 命令端行为权威表述**（其余各处引用本段，不复述）：
> - **不暂停 /sprint-design**：待澄清问题记录归档，不阻塞后续流程（这是不中断原则的精神）
> - 命令端在 Step 1.5 末尾向用户**展示「十、待澄清问题清单」汇总**（按 P0/P1/P2 分组），提示用户在并行进行 /sprint-design 的同时确认待澄清项
> - **仅 P0 数 ≥3 项**时输出"建议先人工裁决再 /sprint-design"的非阻塞提示（不强制暂停），让用户决定
> - 用户后续如裁决与 Agent 暂行方案不同，由 /sprint-bugfix 累进新 Sprint 修订

### Step 2：补充元数据章节（PM Agent）

读取 `.aidp/agents/pm.md` 获取角色定义。在每份研发需求文档**头部**追加以下章节（如 skill 未生成）：

```markdown
## 关联文档

> 路径约定：见 `docs/init/06_版本与用户目录约定.md` §4.x「文档内引用路径的写法」（单一信源，本处不复述）。

| 关系 | 文档 |
|------|------|
| ⬅ 上游输入 | `../产品提供/*.md`（详见下方「源 PRD 清单」）；`memory/productContext.md`；`memory/projectBrief.md`；`docs/requirements/PRD-{项目名}.md`（项目级兜底，仅版本级目录为空时使用） |
| ➡ 下游引用 | `../../../design/detail/{version}/01_详细设计.md`（含 `02_数据库设计.md` / `03_接口设计.md` / 专题文档）；`../../../plans/{version}/01_研发执行计划.md` |
| ↔ 同版本平行 | 单系统：无；多系统：本目录其他 `0N_<系统>.md`（见 `00_索引.md`） |
| 🔗 全局约束 | `docs/architecture/架构约束.md`；`docs/architecture/技术选型.md`；`docs/architecture/UI规范约束.md`；`docs/architecture/架构设计.md` 或 `架构设计/`（如有）|
| ⏮ 跨版本前序 | `../../../requirements/{prev-version}/研发需求/`（如 `{prev-version}` 存在） |

## 源 PRD 清单

| # | 文件 | 简述 | 版本/日期 |
|---|------|------|-----------|
| 1 | docs/requirements/{version}/产品提供/XXX.md | ... | ... |

## ⚠️ 冲突项与解决方案

| # | 主题 | 冲突来源 | 冲突描述 | 采用方案 | 理由 |
|---|------|---------|---------|---------|------|

（无冲突写"无"）

## ❓ 待澄清问题清单导览

| P0（建议先人工裁决） | P1（影响重要分支） | P2（边缘场景） | 总数 |
|---------------------|-------------------|----------------|------|
| Q-XXX, Q-XXX        | Q-XXX             | Q-XXX, Q-XXX   | N    |

（无待澄清写"无"；遵循「⚠️ 不中断原则(Critical)」— 行为权威表述见 Step 1.5「Q-NNN 优先级汇总」段；SKILL 已自动在 PRD 末尾「十、待澄清问题清单」按 7 列表格汇总，每条含 `🔧 Agent 暂行方案`；本头部仅做 P0/P1/P2 计数导览，详情查阅末尾章节）

## ✂️ 已裁剪

| # | 来源 PRD | 裁剪内容 | 裁剪理由 |
|---|---------|---------|---------|

（无裁剪写"无"）
```

**多系统拆分时 `00_索引.md` 额外要求**：在「关联文档」表的「↔ 同版本平行」行必须**逐行列出**所有 `0N_<系统>.md` 分册（含简短范围），并把"分册清单 / 各分册边界 / 跨分册依赖"作为本索引的主体内容。各 `0N_<系统>.md` 内的「↔ 同版本平行」行也要回链 `00_索引.md` 与其他分册。

**业务模块拆分时（同一系统内）**：与多系统拆分同等处理（`01_<模块>.md` 互相回链；`00_索引.md` 列出全部分册）。

### Step 3：更新状态

更新 `memory/{version}/{user}/activeContext.md`：
- 记录研发需求文档已生成（含文件清单 + 是否多系统拆分）
- 如「十、待澄清问题清单」有 P0 等级 ≥3 项 → 标注"建议先人工裁决 P0 项再进 /sprint-design（非阻塞）"
- 当前工作焦点：研发需求已完成（含 Agent 暂行方案的完整 PRD，可并行进 /sprint-design）

