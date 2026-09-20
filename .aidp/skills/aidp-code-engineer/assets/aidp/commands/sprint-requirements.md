# /sprint-requirements — 研发需求生成

你正在执行 `/sprint-requirements` 命令，把**产品提供的需求文档**融合转化为**研发使用的需求文档**。

**★ 本命令是 skill 编排器**：调用 `ux-logic-extractor` skill 生成结构化研发 PRD。

参数：$ARGUMENTS（可选）
- 第 1 位：版本号（如省略，从 AGENTS.md 当前状态读取）
- `--supplement={NN}`：★ 补充模式— 产品在版本开发中途更新了 PRD **或原型**，由 `/version` 检测变更后传入；本命令产出研发需求增量 `NN_<业务主题>.md`（约定 15 统一命名，文件名不带"补充"字眼、补充身份记入 `00_索引.md`）而非覆盖主文档；详见下方「补充模式」段
- `--ledger-cascade`：★ 约定 22 级联落盘 — 由攒批收口子 Agent / `--cascade-now` 即时级联调用；**就地改** `docs/requirements/{version}/研发需求/01_研发需求.md` 正文（多系统按各自 `01_<系统>.md`） + 刷该目录 `00_索引.md` 生成时间；⛔ **不新建任何分册**（`NN_<业务主题>.md` 是产品侧 PRD/原型变更与口述累进的命名空间），⛔ 不产任何中转增量册；与 `--supplement={NN}` 互斥；详见下方「补充模式」段
<!-- dup-check: ignore 四个规划子命令各需在自己参数表里声明，刻意的四份、非漂移 -->
- `--unattended`（可选）：★ **无人值守上下文标记**（由 `/version`·`/sprint-autopilot`·`/sprint-test` 等上游透传）——本命令内**一切 `AskUserQuestion` 与"暂停待用户裁决"一律不弹**，改按下方各门的确定性默认自动推进并留痕；**绝不静默跳过质量门**，只是把"问人"换成"按保守默认走 + 记录"。⛔ 上游传了而本命令不认，flag 会被静默丢弃、在无人值守链里挂死。
  - 本命令的门：系统边界 `unsure`（边界不清需列候选让用户选）→ 无人值守下**按 PRD 显式声明的系统归属**判定，仍不确定则归入"未分类"并在产出头部留痕，不阻塞。

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← `AGENTS.md`「当前状态.当前版本」，读不到则询问。
2. **{user}** ← `git config user.name`

## 目录约定

```
docs/requirements/
├── PRD-{项目名}.md                          # 项目级 PRD（兜底，跨版本稳定）
└── {version}/
    ├── 产品提供/                             # ★ 产品交付的原始 PRD（每版独立）
    │   ├── PRD-XX系统-V0.1.md
    │   ├── PRD-YY系统-V0.1.md
    │   └── ...（可含子目录、可含 docx 转 md 等）
    └── 研发需求/                             # ★ 本命令生成的研发版需求
        ├── 00_索引.md                       # 专职索引（恒有，记文件清单 + 生成时间 + 主/补充标识，约定 15）
        ├── 01_研发需求.md                    # 单系统时（内容主文档从 01_ 起）
        │   或（多系统时，Claude 智能判断）
        ├── 01_XX系统.md
        ├── 02_YY系统.md
        └── 99_待澄清问题清单.md          # ★ 序号 99_ 固定占用；不中断原则的唯一兜底去处
```

**输入优先级**：先扫 `docs/requirements/{version}/产品提供/`，**为空**时再回退到 `docs/requirements/PRD-{项目名}.md`（项目级 PRD）。两者都空则提示用户提供 PRD。

## 前置检查

1. 确认 `docs/requirements/{version}/产品提供/` 目录存在（由 `/version` 或 scaffold 创建；若缺失自动 `mkdir -p`）
2. 扫描输入源：
   - 优先：`docs/requirements/{version}/产品提供/**/*.md`（含 docx 转 md 等）
   - 兜底：`docs/requirements/PRD-*.md`（项目级，仅在版本级目录为空时使用）
   - 都没有 → 提示用户先把产品 PRD 放入 `产品提供/`，然后重跑
3. 检查 `docs/prototype/{version}/code/` 是否存在原型（可选输入，无则跳过）
4. 确认 `memory/productContext.md` 存在

## 执行步骤

**★ QR 变更范围裁剪协议接线（必须传，别让增量迭代付全量 QR 的代价）**：`ux-logic-extractor` 的质量检查支持按本轮变更范围裁剪，**唯一入参 = `qr_delta_scope`（可选，不传 = 全量）**。⛔ 命令端**不得自造 `qr_mode`**——该 SKILL 从未定义它（`qr_mode` 是 `dev-manual-testcase` 独有概念），凭空传等于修改 SKILL 契约（违反约定 21）且被静默忽略。命令端按下面两条传：

- **全量生成**（首次规划 / 主文档重生成）→ **不传 `qr_delta_scope`**（SKILL 契约：不传 = 全量）。
- **增量补充**（`/version` 补充模式〔情况 B-2〕检出 PRD/原型变更后**派发本命令并传入** `--supplement={NN}`；⛔ `/version` 自身没有 `--supplement` flag，别照字面去敲）或 `/sprint-dev` 口述累进 → 传 `qr_delta_scope = <本轮 NN_<业务主题>.md 的专题名 / 章节清单>`。
- ⛔ **只裁「语义核对」的范围，机器门一律全量跑**（SKILL 明文，标「全量」档的维度不接受裁剪——它们的失效形态正是「新增这一处与旧的那些不一致」，只看增量内部一个都发现不了）。算不出 Δ 就退回全量并注明，**宁可多算一个专题、绝不漏传播一处语义**。

> **关键规则（约定 21）**：本命令是 `ux-logic-extractor` skill 编排器——**SKILL 内规则为单一信源**（模式判定 / 拆分数量 / 不中断原则 / 不臆造兜底 / 上游溯源 / Q-NNN 编号等），命令端只做**传参 + AIDP 编排后处理**，不复述、不修改 SKILL 维度。
>
> **进入本段第一动作 = Read `.aidp/flows/sprint-requirements/execution-steps.md`**，逐项执行 Step 0–3、绝不凭下方骨架表或记忆略过子步骤（尤其 Step 1.5 的 (a)~(e) 后处理 + SKILL 脚本复核）。

| Step | 职责（骨架，详情见 flow 文件） |
|------|-------------------------------|
| Step 0 | 输入扫描（产品提供/ 优先、PRD-*.md 兜底）+ 多系统智能判断（single / multi / unsure）|
| Step 1 | 调 `ux-logic-extractor` skill 生成融合研发 PRD；传严格模式信号（上游齐全）+ 输出路径约定（`00_索引.md` + `01_研发需求.md`）|
| Step 1.5 | 命令级后处理 (a)~(e)：多系统拆分 / 多 PRD 冲突 / 待澄清标注 / 裁剪 / SKILL 脚本复核（派子 Agent，清单以 SKILL 为准） |
| Step 2 | 补充元数据章节（PM Agent）：关联文档 / 源 PRD 清单 / 冲突项 / 待澄清导览 / 已裁剪 |
| Step 3 | 更新 `memory/{version}/{user}/activeContext.md` |
## 输出

```
✅ /sprint-requirements 完成（{version}）

📋 输入源：
- 产品 PRD：{N} 份（来自 docs/requirements/{version}/产品提供/）
- 原型代码：{有 / 无}
- 模式：{single / multi}

📋 生成的文件：
- docs/requirements/{version}/研发需求/00_索引.md（专职索引，恒有）
- docs/requirements/{version}/研发需求/01_研发需求.md
  或（多系统拆分）：
- docs/requirements/{version}/研发需求/00_索引.md
- docs/requirements/{version}/研发需求/01_XX系统.md
- docs/requirements/{version}/研发需求/02_YY系统.md
- docs/requirements/{version}/研发需求/99_待澄清问题清单.md（★ 有待澄清项时必产；PRD 条目被裁剪/存疑一律登记到此，⛔ 不得只写进「✂️ 已裁剪」表——那不是待澄清清单）

内容摘要：
- 功能模块：{N} 个（P0: {N} / P1: {N} / P2: {N}）
- 冲突项：{N} 个（已记录解决方案）
- 待澄清问题清单：{N} 个（P0: {N} / P1: {N} / P2: {N}；** 不阻塞 /sprint-design**，建议并行确认）
- 已裁剪：{N} 个

（**Sprint 拆分与排期不在本命令的产出范围**，由后续 `/sprint-plan` 生成 `01_研发执行计划.md`）

📌 下一步：
- 若 {待澄清}=0 → /sprint-design（生成详细设计）
- 若 {待澄清}>0 → 可并行进 /sprint-design，同时向产品确认 Q-NNN 回填到「❓ 待澄清」章节（不阻塞；P0 ≥ 3 时建议先人工裁决）
```

---

## 拆分规则（约定 15 细则）

> 完整阈值表见 `docs/init/02_迭代输入指导.md §10.4`。

- **single 模式**：`00_索引.md` + `01_研发需求.md`；**是否拆分由 `ux-logic-extractor` SKILL「拆分触发条件」判定**（单一信源，命令端不写死行数/模块数阈值——写死必与 SKILL 漂移，一旦命令端阈值宽于 SKILL 就会该拆不拆），命中即拆为
  `00_索引.md` + `01_<模块>.md` / `02_<模块>.md`
- **multi 模式**：按系统拆分（每个系统一份），并加 `00_索引.md`；如某个系统内部还过大，二级再按模块拆为 `01_<系统>-用户模块.md` 等

下游命令（`sprint-design` / `sprint-dev` / `sprint-test`）通过 glob
`docs/requirements/{version}/研发需求/*.md` 读取全部分册，无需关心是否拆分。

---

## 补充模式（`--supplement={NN}`）

当版本开发中途产品更新了 PRD **或原型**，由 `/version` 检测到 `docs/requirements/{version}/产品提供/**/*.md` 或 `docs/prototype/{version}/{code,mockup}/**` 与上次快照不同时，调用本命令并传入 `--supplement={NN}`。本节描述补充模式下的差异化行为，**fresh 模式（无此参数）保持原流程不变**。

> ⚠️ `--supplement={NN}` 是**本命令的 CLI 参数**，不是 ux-logic-extractor SKILL 的参数：SKILL 无 `mode=supplement` 之类的模式开关，增量完全由调用方在 prompt 中描述（见下方「输入差异」第 4 条）。命令端按 SKILL「prompt 驱动增量」契约调用，**不向 SKILL 传任何 mode 参数**。


### ★ 约定 22 级联落盘（`--ledger-cascade`，与 `--supplement={NN}` 互斥，同时传则报错）

由**约定 22 级联**调用时（攒批收口子 Agent / `--cascade-now` 即时级联）**必须**加 `--ledger-cascade`：**就地改内容主文档正文** `docs/requirements/{version}/研发需求/01_研发需求.md`（多系统按各自 `01_<系统>.md`），改完刷该目录 `00_索引.md` 生成时间（约定 15）。
⛔ 不新建 `NN_` 分册、不产中转增量册、不全量扫 `code/` 等落盘细则与内容产出方式，**单一信源 = `.aidp/reference/开发期族增量.md`「收口执行要点」第 2/3 条（L1 需求）**，本命令不复述。

### 输入差异
- **必读** `docs/requirements/{version}/研发需求/输入变更-{NN}.md`（由 /version Step 2.4.0 生成 — 含 PRD 与原型两类变更的摘要 + diff + 受影响范围预估）
- **必读** 原主文档 `docs/requirements/{version}/研发需求/01_研发需求.md`（历史裸 `00_研发需求.md` / 无前缀 `研发需求.md` 兼容；基线，只读不修改）
- **必读**（如有原型变更）当前 `docs/prototype/{version}/code/` + `docs/prototype/{version}/mockup/`（变更后版本，用 ux-logic-extractor 模式 B 重新对齐 UI 交互逻辑）
- **传给 skill 的 prompt 必须显式说明**：「本次仅针对 PRD / 原型变更点产出增量需求，未变内容不重复；每条增量需求标注关联的输入变更摘要小节（PRD 变更 / 原型变更）」

### 输出差异
- **不**覆盖主文档 `01_研发需求.md`（历史裸 `00_研发需求.md` 兼容；或多文件+前缀形态如 `01_版本背景.md`~`07_排除项.md`，也不动）
- 新增增量文档 — **按 AGENTS.md 约定 15「补充文档命名规则」生成**，统一 `NN_<业务主题>.md`（文件名不带"补充"字眼；NN 续编内容主文档目录现存最大序号 +1）：
  - 主文档**单文件**（当前布局即 `01_研发需求.md`；历史裸 `00_研发需求.md` / 无前缀 `研发需求.md` 兼容）→ 增量从续编序号起 `NN_<业务主题>.md`
  - 主文档**多文件+前缀**（如 `01_版本背景.md`~`07_排除项.md`）→ 续编主序号：`{MAX+1}_<业务主题>.md`（例：`08_货币元积分双单位展示改造.md`），共享 NN={NN} 写文档头部第一段「本补充信息」段
  - 内容大触发拆分阈值 → 拆为 `{NEXT}_<业务主题>/00_索引.md` + `0M_*.md`
- **★ 命名保持**：上游 ux-logic-extractor SKILL 输出新风格 `NN_业务名.md`（已禁"补充/追加"语义前缀），命令端在 SKILL 返回后**只做序号续编校正**（若 NN 与目录现存最大序号冲突则 `git mv` 归一到 `MAX+1`），**绝不回补"补充"字眼**（具体脚本见 `.aidp/flows/version/planning-4.md`（`version.md` Step 2.4.4 现仅是一行指针），本命令单独被调用时也跑同段脚本兜底）
- **业务主题来源**：① 用户调 `/sprint-requirements {version} --supplement={NN} "<主题>"` 显式传入；② 从口述补充文件 `docs/requirements/{version}/产品提供/v{X}-补充-{NN}-<主题>.md` 文件名解析；③ 兜底用 `增量NN{NN}`
- 在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间，**用归一后的真实路径**）
- 增量文档自身的「关联文档」表：⬅ 上游加 `../输入变更-{NN}.md` + 本目录 `00_索引.md`（回链）；↔ 同版本平行回链主文档与同轮其他增量
- "❓ 待澄清"/"⚠️ 冲突项"等元数据表如本次变更产生新条目 → 写在补充文档自己的头部，不污染主文档
