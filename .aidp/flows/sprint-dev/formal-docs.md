# /sprint-dev — 分支 B，Phase 0B.1.1 契约放行与正式成文配方

> 本片覆盖：分支 B，Phase 0B.1.1 契约放行与正式成文配方。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

### Phase 0B.1.1：★ 自动文档增量流

**触发条件**：分支 B 必跑契约放行；以下正式成文配方仅 document 已授权时执行，未授权记 NOT_REQUESTED、保留最小规格与事实登记；`skip-doc-sync` 只影响成文调度，不能跳过规格、反转清算、台账或 M/L 完成门。

**第一动作 = Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`**，按“契约卡放行”先判档、写卡与四族义务，再分流。该片是分档时机与并行汇合的唯一权威；下方步骤 1–6 是**正式成文配方**，不能对所有档位无条件串行执行。
- **S**：先契约卡＋受影响四族短行，跳过下方完整成文配方进入 Phase 0B.1.3/0B.2；用例按本节配方步骤 4 判定并双重登记，required=true 时正式用例必须生成，不能把卡的 AC 当用例。后续完整成文由约定 22 收口或显式 `--cascade-now` 负责。
- **M**：契约卡放行后启动 Sprint，Phase 1 同时派代码与 docs；docs 按下面配方依次成文，**完整文档硬门移到本轮汇合、先于 `/sprint-test`**。主流程记录 docs owner/任务/写集，不能把文档义务交给无人负责的末尾兜底。
- **L**：下面配方与完整文档硬门均在开发前完成，再进入 Phase 1。
- **Step X.0.0**：检测实现期新增漂移、复核实际档位、主流程登记工作单；不重新生成 docs 已完成的同一批内容。正式补充与台账合并仍各走 `--supplement` / `--ledger-cascade`，不能混用落点。

**典型场景**：产品口述新功能 → 研发用 `/sprint-dev "<描述>"` 直接开发 → 历史问题是只追代码不追文档 → 现在用本流程自动追平。

**正式成文配方**（L 开发前、M docs 分支、S 收口时执行；docs 内按依赖串行，代码可按契约并行。任一步失败记缺项，交原 docs Agent 修正；确需产品决策才待裁决，不静默放行）：

1. **记录口述补充**：由主流程把命令参数 `"<描述>"` + 当前时间 + developer_identity 写入来源文件；契约放行时已经创建则复用同一文件，docs 不重复创建：
   `docs/requirements/{version}/产品提供/口述补充-{YYYYMMDD-HHMM}.md`（每次累进一份；用时间戳区分多次口述；该目录已有 PRD 时本文件作为同级补充）

2. **生成研发需求补充**：经 `/sprint-requirements {version} --supplement={NN} [--unattended]` 编排（研发需求唯一入口，内部调 `ux-logic-extractor` skill 增量补充、prompt 驱动；★ **不直调 SKILL**——直调会跳过命令端的落盘归一 / 多系统拆分 / 头部元数据表 / AIDP 硬规范回检，与同轮其余三层 `/sprint-design --supplement [--unattended]` · `/sprint-plan --supplement [--unattended]` · `/sprint-selftest --supplement [--unattended]` 走命令中介保持一致），输入：
   - 口述补充文件（步骤 1 产出）
   - 当前 `docs/requirements/{version}/研发需求/01_研发需求.md`（既存基线；历史裸 `00_研发需求.md` 兼容）
   - 当前 `docs/prototype/{version}/code/` + `mockup/`（如有，作为交互细节参考）

   输出研发需求增量文档（NN 按目录现有序号累进），并在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间）。

   > ★ **增量文档命名（按约定 15）**：所有增量文档统一 `NN_<业务主题>.md`（NN 续编目录现存最大序号 +1，排除 `00_索引`/`98_`/`99_`）——**文件名不带"补充"字眼**；补充身份只记入 `00_索引.md`（类型=补充 + 更晚生成时间）。上游 SKILL 本就产出干净 `NN_<业务名>.md`（已禁"补充/追加"语义前缀，各 SKILL 的 `check_doc_split.py` 亦禁），命令端**只做序号续编校正、绝不回补"补充"字眼** + 维护 `00_索引.md`（脚本见 `{{AIDP_HOME}}/flows/version/planning-4.md`（`version.md` Step 2.4.4 现仅是一行指针））。下文括注（如"研发需求增量"）仅标识增量内容所属文档类型。

   skill 内置的不中断原则、数据闭环完整性等会自动生效（沿用主文档 `Q-NNN` 编号空间往后递增，数据闭环孤立端用 `Q-FLOW-NNN`），命令端按 AGENTS.md 约定 21 不复述具体条款，详见 `{{AIDP_HOME}}/skills/ux-logic-extractor/SKILL.md`。

2.5. **★ 口述规模档位判定门（`sup_scale`）——开发前已生产，此处复核并传递**

   判据与字段的单一信源 = `flows/sprint-dev/incremental-contract.md`“契约卡放行”。**判档发生在步骤 1/2 成文之前**，不能先跑完整需求 SKILL 再决定是否需要它。复用 `versions.{V}.sprints.{新NNN}.dev_scale`，并保留 `versions.{V}.sprints.{新NNN}.sup_scale` 的 REQ/PAGE/第三方等原字段，两者 tier 相同；正式需求揭示了新表/破坏性变化时立即升 L、重过开发前门。

   **S（语义子档）**的「受影响结论清单」仍逐条包含落点、file:line、旧结论、新结论、失效/改写/不受影响；写入契约卡，正式需求成文时回链。空表或整体描述不算完成，约定 34 安全性回答不可省。

   以下正式调用仍显式传 `--scale={档位}`，只写 baseline 不传参视为未执行档位策略。M 设计合册另带 `--compact-contract=<契约卡路径>`，命令端记录版式映射，不能谎称上游 scale=M 原生输出一册。

3. **触发增量设计**：调 `/sprint-design {version} --supplement={NN} --scale={档位} [--unattended]` 派生增量设计；M 另带 `--compact-contract=<契约卡路径>`，设计/接口默认合册、保留上游强制独立专题：
   - Step 0.6.4.7 全扫 code/ 拿当前代码现状（含本 sprint 即将新增功能可能已部分实现的情形）
   - Step 0.3 按四象限对比口述新功能 vs 代码现状：判定走"② 新增"还是"③ 代码超前-补写"
   - 以增量 prompt 驱动调 dev-logic-architect（按其 SKILL 增量约定，无 mode 参数）产出详细设计 / 接口设计 / 数据库设计的补充文档（均归一为 `NN_<业务主题>.md`，按实际范围）
   - **★ 路径占位符显式传参**：调 dev-logic-architect 补充时，必须显式传 `docs/init/06_版本与用户目录约定.md` §2.5.7 映射表的 5 个占位符值，禁止 SKILL 自动推断

3bis. **★ 触发增量研发执行计划（独立一步，不能并进步骤 3）**：调 `/sprint-plan {version} --supplement={NN} --scale={档位} [--unattended]` 产出 `docs/plans/{version}/NN_<业务主题>.md`。
   > ⛔ **`/sprint-design` 不产研发执行计划**——它全文不涉及 `dev-execution-planner`，其补充模式产物只有 详细设计 / 接口设计 / 对外开放接口 / 数据库设计 / DDL SQL 五类。⛔ 因此**不得把"计划增量"并进步骤 3**——那会让下方硬门第 6 项（**不可 N/A 的必 Pass 项**）无人生产、恒 Fail。成因见 `{{AIDP_HOME}}/flows/sprint-dev/rationale.md`「计划增量为何必须独立一步」。
   > 即便临场改为直调 `dev-execution-planner` 兜住，也会绕过 `/sprint-plan` 的 Step 1.5 三脚本回检、Step 1.6 SQL 路径回写、Step 2 关联文档注入——故必须走命令编排、不得直调 SKILL。

4. **★ 研发自测用例适用性（先判后生成）**：主流程执行 `check_case_ledger_pending.py --prepare` 读取真实外层意图，将读数交 docs；`required=true` 才生成正式用例，`false` 则双重登记欠账后跳到步骤 5。S 同样执行本判定，不能因为跳过成文配方而漏掉它。确需正式用例而缺增量计划时先通过既有生成链补齐必要上游输入，不能给 SKILL 假计划或拿卡的 AC 充正式用例。纯技术内部调整也必须留痕，不能只打印 WARN。

   | 外层意图 | prepare 参数 | 行为 |
   |---|---|---|
   | autopilot 安排后续实测 | `--context autopilot` | 本轮生成 |
   | sprint-batch 未跳过 Step 6 | `--context batch` | 本轮生成 |
   | direct 只开发，或 batch 已跳过实测 | `--context direct`；或 `--context batch --skip-aiauto-test` | 双重登记延期 |
   | 用户显式要求实测，或父链传 `--aiauto-test-required` | 对应 context 加 `--require` | 必须生成（优先于子批次局部 skip） |

   ```bash
   python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version "{version}" --sprint "{新NNN}" \
     --prepare --context "{direct|batch|autopilot}" --reason "{本轮实际实测安排}" --json
   # 按上表附加 --require 或 --skip-aiauto-test；非零退出先修状态，不继续。
   ```

   下列生成动作仅在 `required=true` 时执行：经 `/sprint-selftest {version} --supplement={NN} --scale={档位} [--unattended]` 编排（研发自测唯一入口，内部调 `dev-manual-testcase` skill 增量补充，prompt 驱动），输入：
   - `NN_<业务主题>.md`（研发需求增量，步骤 2 产出，本次新增 / 修订的功能点）
   - `NN_<业务主题>.md`（详细设计 / 接口设计 / 研发执行计划增量，步骤 3 产出，与功能点关联的接口/页面/任务）
   - 原研发自测用例（`研发自测/02_自测用例-总览.md`（多文件）或 `研发自测/02_全量自测用例.md`（单文件）；研发自测方案 `研发自测/01_研发自测方案.md`；旧锚布局兜底 `研发自测/01_自测用例-总览.md`·`研发自测/00_研发自测方案.md`·`研发自测/00_研发自测.md`；基线，只读）
   - `code/` 已有代码
   - **★ 路径占位符显式传参**：必须显式传 `{测试文档目录}=docs/testing/`（覆盖 SKILL 默认 `docs/test/`；映射表见 `docs/init/06` §2.5.7）

   skill 工作要求：仅针对本轮新增/修订的功能点输出新用例或修订用例，未变功能不重复；原型变更必须重新对齐"操作对象 + 预期现象"。skill 内置的数据一致性与溯源原则 + 上游引用规则会自动生效，命令端按 AGENTS.md 约定 21 不复述，详见 `{{AIDP_HOME}}/skills/dev-manual-testcase/SKILL.md`。

   输出 `docs/testing/{version}/研发自测/<NN>_<业务主题>.md`（按 AGENTS.md 约定 15 统一数字前缀规则：NN = 目录现存最大序号 + 1、用例从 `02_` 起，文件名不带"补充"字眼；★ **一律在 `研发自测/` 同目录平铺续编、严禁再拆二级子目录**——SKILL「文件命名总则」要求同目录 `NN_` 前缀平铺，其硬门 `check_testcase_format.py` 只 `glob("*.md")` 非递归，落进子目录的用例会整体逃检），并在**研发自测专职索引** `00_索引.md`（及 `01_研发自测方案.md` 的「用例索引」段 / `02_自测用例-总览.md`）追加登记该增量（研发自测目录已对齐通用范式、导航锚 = `00_索引.md`，见约定 15）。新增用例 ID 全局唯一（继承原主文档编号空间，往后递增）。

   **延期终态**：`--prepare` 返回 `required=false` 即已把状态写入 baseline 和用例族增量册；不用额外重复 `--defer`。后续 `/sprint-aiauto-test` 必须先生成这些用例，不允许沿用该 false 跳过显式测试请求。

**步骤 4 完成后硬收口**：若本轮 `aiauto_test_required=true`，正式用例文件已经生成且用例族增量已由 `--ledger-cascade` 收口，必须执行：

```bash
python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version "{version}" \
  --sprint "{新NNN}" --complete --reason "正式研发自测用例已生成并通过用例族级联前置门" || exit 1
```

5. **更新各目录导航锚**：本轮新增的 6 类增量文档在对应目录导航锚各追加一行（类型=补充 + 生成时间）——研发需求 / 详细设计 / 接口设计 / 数据库设计 / 研发执行计划 / **研发自测用例**均 → `00_索引.md`（研发自测已对齐通用范式，另在 `01_研发自测方案.md` §8 用例索引段同步登记业务导航）

6. **完成回传**：列明已生成的需求/设计/计划与当前契约修订；用例真实二选一写「正式用例已生成并通过回检」或「延期并已双重登记，待实测前补齐」。M docs 回主流程汇合，L 回开发前放行，S 收口回成文结果；不得重复启动 Sprint、不得在延期状态宣称已生成用例。

**★ Phase 0B.1.1 正式文档硬门（L 开发前 / M 汇合时 / S 显式成文时）**：

> 契约放行由 `incremental-contract.md` 负责；下表核正式产物，**不把 S/M 的开发前契约门替换成六册存在性门**。L 未通过不得开发；M 未通过不得进入 `/sprint-test` 或宣称本轮交付完成；S 默认只契约＋台账，不虚报正式文档/用例已经生成。成文失败交原 docs Agent 补齐，不自由反问“要不要补”。

| # | 校验项 | Pass 判据 | Fail 处置 |
|---|--------|-----------|-----------|
| 1 | 口述补充落盘 | `docs/requirements/{version}/产品提供/口述补充-*.md` 存在且非空 | 补写步骤 1 |
| 2 | 研发需求补充 | `docs/requirements/{version}/研发需求/NN_*.md`（本轮 NN）已生成 | 回步骤 2 重跑 `ux-logic-extractor` |
| 3 | 详细设计补充 | `docs/design/detail/{version}/NN_*.md`（详细设计）已生成 | 回步骤 3 重跑 `/sprint-design --supplement [--unattended]` |
| 4 | 接口设计补充 | 本轮涉及接口 → 接口设计增量已生成；不涉接口 → 标 N/A | 涉接口却缺 → 回步骤 3 |
| 5 | 数据库设计补充 | 本轮涉及表/字段 → 数据库设计增量已生成；不涉库 → 标 N/A | 涉库却缺 → 回步骤 3 |
| 6 | 研发执行计划补充 | `docs/plans/{version}/NN_*.md`（研发执行计划增量）已生成 | 回**步骤 3bis** 重跑 `/sprint-plan --supplement [--unattended]`（⛔ 不是步骤 3，`/sprint-design` 不产计划） |
| 7 | 研发自测用例补充 | `docs/testing/{version}/研发自测/NN_*.md` 已生成；或 `--prepare` 明确延期、baseline 与用例增量册双重留痕（含纯技术内部调整） | required=true 却缺用例，或延期未留痕 → 回步骤 4 |
| 8 | 各目录 `00_索引.md` 登记 | 上述已生成的增量在对应目录 `00_索引.md` 均有"类型=补充 + 生成时间"登记行 | 缺登记 → 回步骤 5 补登记 |

- **N/A 合法**：项 4/5 在本轮确无对应变更时、项 7 在步骤 4 明确延期且双重留痕时标 N/A（附一句判据，如"本轮无接口变更"）即算 Pass；项 1/2/3/6/8 为**必 Pass 项**，不可 N/A。
- **M 合册同样算 Pass**：项 3/4/5 按实际合册中的详细设计/接口/数据库章节及契约回链核对，不要求三个独立文件；适用内容缺失仍 Fail。上游强制独立专题照旧。
- **S 契约放行不等于正式成文通过**：契约卡＋台账缺一即 Fail；语义子档的「受影响结论清单」须逐条有处置。正式成文时按 `--supplement` 新增或 `--ledger-cascade` 合入既有册并刷新索引，不能虚报。
- **`skip-doc-sync` 不豁免 M/L 完成硬门**：已延期的义务保留可发现状态，不能仅凭 WARN 返回成功。
- **无人值守（`--unattended`）同样受硬门约束**：Fail 项按上表"Fail 处置"自动重跑对应 SKILL；重跑仍 Fail → 转失败处置（熔断冻结 + #4 里程碑通知 WARN），**不挂起、也不放行带病开发**。

**显式延期**：`skip-doc-sync` 下仍须记录口述、完成契约卡与反转门，主流程原子取号后把本轮口述变更写进受影响各族台账（见 `{{AIDP_HOME}}/reference/开发期族增量.md`）。S 可以带已登记成文义务继续；M 必须在汇合时补齐、L 必须开发前补齐，不能用该参数宣告缺件通过。台账与工作单是后续可发现的输入，终端 WARN 不能替代落盘。

> 编号说明：Phase 0B.1.2 为退役编号、不使用（保留以免改动他处对 0B.1.3 的直引）。


按上述 S/M/L 时机完成契约放行或正式文档门后，Read `{{AIDP_HOME}}/flows/sprint-dev/formal-reversal.md`。M docs 分支保留本片配方并在 test 前汇合，S 不无条件执行完整成文配方。
