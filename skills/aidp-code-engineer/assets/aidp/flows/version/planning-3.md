# /version · 版本规划流程详情 — 分片 3/8

> 本片覆盖：**Step 2.4.1 requirements / 2.4.2 design / 2.4.3 plan / 2.4.3.5 selftest**。
> 完整分片清单见 `{{AIDP_HOME}}/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
#### Step 2.4.1：调用 /sprint-requirements

**fresh 模式**：

```
执行：/sprint-requirements {version} [--unattended]

该命令会调用 ux-logic-extractor skill 生成需求文档
输出：docs/requirements/{version}/研发需求/00_索引.md + 01_研发需求.md（命令端 Step 2.4.4 归一 + 生成 00_索引）
```

**补充模式**（情况 B-2）：

```
执行：/sprint-requirements {version} --supplement={NN} [--unattended]

额外 prompt 输入（命令端写入 skill 调用上下文）：
- 输入变更摘要：docs/requirements/{version}/研发需求/输入变更-{NN}.md（必传，含 PRD 与原型两类变更）
- 当前原型（变更后）：docs/prototype/{version}/code/ + docs/prototype/{version}/mockup/（让 skill 模式 B 重新对齐 UI 交互细节）
- 原主文档作为基线：docs/requirements/{version}/研发需求/01_研发需求.md（只读，不修改；历史裸 `00_研发需求.md` 兼容）

skill 工作要求（命令端在 prompt 里指明）：
- 仅针对 PRD / 原型变更点产出"增量需求"，不重复未变内容
- 对每条增量需求标注关联的输入变更摘要的具体小节（PRD 变更 / 原型变更）

落盘：docs/requirements/{version}/研发需求/NN_<业务主题>.md（研发需求增量，文件名不带"补充"字眼）
回写：在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间 + 关联输入变更），见 Step 2.4.5.5（`planning-5.md`）
```

等待 `/sprint-requirements` 完成后再继续。

#### Step 2.4.1.5：★ 需求规模档位判定门（P0-5 — 小需求不走大流程，产物按规模伸缩）

**动机**：无论"改一个按钮"还是"新建业务域"，规划期一律产满全套（3~9 册设计 + 全量用例 + 独立分册计划）→ 文档:代码严重失配（实测某版 9.4:1）、规划耗时数小时。故在需求产出后、设计前先判规模档位，把裁剪指令传给后续设计/计划/自测 SKILL。

**判据（据 Step 2.4.1 产出的研发需求 + 原型 + 需求内 DDL 预判，命令端确定性计算）**：`REQ_COUNT`=研发需求条目数 · `PAGE_COUNT`=涉及页面/原型数 · `HAS_DDL`=是否新建表 · `THIRD_PARTY`=第三方对接**深度**（**四值，⛔ 不是布尔**，取值见下表）。

**`THIRD_PARTY` 四值判定（按序取第一个命中；⛔ 布尔化会把"只消费既有上游新加的字段"误升到 L）**：

| 取值 | 判据 | 对档位的作用 |
|------|------|------|
| `new-system` | 接入一个**从未对接过**的第三方/上游系统 | **≥ L**（联调面、鉴权、错误契约、降级全是新的）|
| `endpoint-level` | 既有上游**新增端点**需要对接 | **≥ M**（契约是新的，但集成基座已有）|
| `field-level` | **只消费既有上游既有端点新加的字段**，零新增端点 | **不抬档**，按 REQ/PAGE 正常判 |
| `none` | 无第三方对接变化 | 不抬档 |

> **⛔ 不计入 `THIRD_PARTY` 的一类**：「登记上游**尚未开放**的能力 + 本方已 fail-closed 兜底」。
> 它不增加本版任何实现复杂度，只增加一条待澄清条目（走 `99_待澄清问题清单.md`）。
> 把它算成第三方对接，等于让"我们什么都没做"抬高整版产物规模。
>
> **判定证据取自研发需求**：`ux-logic-extractor` 的 `CAP-OUT/IN-NNN` 与 `REQ-3P[-CB]-NNN`
> 编号体系已区分能力方向与回调；**新增 `CAP-IN`/`CAP-OUT` 条目 = 端点级及以上**，
> 只在既有条目下补字段 = `field-level`。判不准时按**高档**取值（安全兜底）。

| 档位 | 判据 | 设计册数 | 用例数建议 | 任务详情 |
|------|------|---------|-----------|---------|
| **S** | `REQ≤5 且 PAGE≤2 且 !HAS_DDL 且 THIRD_PARTY ∈ {none, field-level}` | 1 册合并（详设/接口/数据库并一份） | 25~40 | 并入执行计划、不单独分册 |
| **M** | `REQ≤15 或 PAGE≤5`（未命中 S），或 `THIRD_PARTY = endpoint-level` | 3 册（详设/接口/数据库） | 60~100 | 正常分册（按 Phase 拆，册数以 `dev-execution-planner` SKILL 为准）|
| **L** | 超出 M，或含建表，或 `THIRD_PARTY = new-system` | 现状全套 | 现状全套（按**每模块**基线，口径见 SKILL 维度 19；⛔ 不与 S/M 的整轮合计数比大小）| 现状全套 |

**判定顺序**：先判是否命中 S（四条全满足）→ 否则 M（`REQ≤15 或 PAGE≤5`）→ 否则 L；再用兜底抬档——**含建表 / `new-system` 一律 ≥ L，`endpoint-level` 一律 ≥ M**（涉及数据模型 / 全新外部集成的复杂度不可低估；但**只消费新字段**的复杂度也不可高估）。

**用户覆盖**：`/version` 带 `--scale=S|M|L` 显式覆盖自动判定（审计留痕 `source:"user"`）。

**落盘 + 传递**：
- 判定结果写 baseline `versions.{V}.req_scale`（`{tier, req_count, page_count, has_ddl, third_party:"none|field-level|endpoint-level|new-system", source:"auto"|"user", at}`）——**留痕供复核与下游传参**（本轮实际传给各 SKILL 的档位、以及 Step 2.4.4 的收敛兜底都读它）。
- **把裁剪指令作为项目级上下文传给后续 Step 2.4.2 / 2.4.3 / 2.4.3.5 的 SKILL 调用**（约定 21 命令端项目级延伸，不改 SKILL 单一信源）：调 `/sprint-design`·`/sprint-plan`·`/sprint-selftest` 时随调用传 `scale=S|M|L`（并附「目标产出（设计册数 / 用例数区间 / task 是否分册）」作自然语言冗余表述）。`dev-logic-architect` / `dev-execution-planner` / `dev-manual-testcase` 三个 SKILL 均已内置「需求规模档位」入参并据此伸缩产出（缺省或识别不到 → 回退 L 档现状全套），命令端只需**正确传档**、不必替 SKILL 做裁剪。
- **⚠️ 用例数基线机检须显式传档位**：核验研发自测用例数量基线时跑 `check_case_stats.py <路径> --scale <档位>`（S=25~40 / M=60~100，整轮合计口径）——**不传 `--scale` 脚本按 L 档行为跑、只判 20 条硬下限**，S/M 档会漏判。
- **异常路径兜底**：若 SKILL 未按传入档位收敛产出（如 S 档仍产出多册设计），命令端在归一 Step 2.4.4 按档位做产物合并兜底——S 档把多份设计合并为 1 册。此为异常兜底、非常规路径，触发时应在打印里标注 `档位收敛异常（已兜底合并）`。
- **⛔ 档位只伸缩产出规模，绝不放松任何 Critical 硬门**：PRD 功规点 100% 覆盖、上游溯源、字段核对、version-auditor 八项在任何档位下都不跳过——S 档只是承载文件更少更薄，不是少做校验。

**打印**（第三方位打**四值本身**，⛔ 不打"是/否"——布尔化的打印会让误判无从复核）：
`📐 需求规模档位：S（REQ=3 PAGE=2 建表=否 第三方=field-level）→ 设计合并 1 册 / 用例 25~40 / task 并入计划`。

#### Step 2.4.1.6：★ 测试环境与账号前置继承（与 2.4.2/2.4.3 并行，不占串行链）

`01_测试环境与账号.md` 是 `/sprint-aiauto-test` Phase 0.0.5 与 `auto-test-runner` 的
**机器消费权威**，但它的内容**主体来自"继承上一版 + 本版环境探测"**，与详细设计 / 执行计划的
产物**零数据依赖**——却被压在串行链最末的 Step 2.4.3.5 里等。代价不是那几分钟，是**测试链路
在整个规划期内都没有可用的环境信息**：`/sprint-aiauto-test` 此时被唤起只能整批 `block`。

**本步动作（轻量，不调 SKILL）**：

```bash
DST="docs/testing/{version}/研发自测/01_测试环境与账号.md"
if [ -f "$DST" ]; then
  echo "🔑 测试环境与账号：已存在，跳过"
else
  # 上一版本 = 版本号排序里紧挨着本版的前一个（本版目录此时可能尚未建，故先剔除本版再取末位）
  SRC=$(ls -1d docs/testing/V*/研发自测/01_测试环境与账号.md 2>/dev/null \
        | grep -v "/{version}/" | sort -V | tail -1)
  if [ -n "$SRC" ]; then
    mkdir -p "$(dirname "$DST")" && cp "$SRC" "$DST"
    echo "🔑 测试环境与账号：继承自 $SRC（待 2.4.3.5 校准）"
  else
    echo "🔑 测试环境与账号：无可继承源，跳过（由 Step 2.4.3.5 首次生成）"
  fi
fi
```

继承下来的文件**头部必须加一行** `> ⚠️ 继承自 {上一版本}，尚未按本版校准（Step 2.4.3.5 校准）`。

**边界（三条，缺一则本步变成漏洞而非加速）**：
- ⛔ **只在文件不存在时继承**——已有内容一律不覆盖（约定 38 的随口归档随时可能已经写过它，
  覆盖等于把用户当场给的真环境换成上一版的旧地址）。
- ⛔ **不是生产步骤**：`01_测试环境与账号.md` 的**唯一生产者仍是 Step 2.4.3.5 的
  `/sprint-selftest`**，本步产出的是**带告警横幅的继承草稿**；2.4.3.5 到达时按既有的
  **增量校准**行为处理（同约定 38 的"追加新行 + 备注来源时间、不动旧行"），不重新生成。
- ⛔ **不进硬门**：继承不到（首版 / 上一版没这文件）→ 打印一行跳过即可，**不失败**。

**打印**：`🔑 测试环境与账号：继承自 {上一版本}（待 2.4.3.5 校准） | 已存在，跳过 | 无可继承源，跳过`。

#### Step 2.4.2：调用 /sprint-design

**fresh 模式**：

```
执行：/sprint-design {version} --scale={档位} [--unattended]      # 档位 = Step 2.4.1.5 判定的 req_scale.tier（S|M|L）

该命令会调用 dev-logic-architect skill 生成详细设计
输出（命令端 Step 2.4.4 归一为 00_索引 + 01_/02_/03_）：
- docs/design/detail/{version}/00_索引.md
- docs/design/detail/{version}/01_详细设计.md
- docs/design/detail/{version}/02_数据库设计.md
- docs/design/detail/{version}/03_接口设计.md
- docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql（中文命名 + 两位数字序号前缀；`99_回滚脚本.sql` 序号保留；详见 /sprint-design Step 3 与 `dev-logic-architect` SKILL Module D）
```

**补充模式**（情况 B-2）：

```
执行：/sprint-design {version} --supplement={NN} --scale={档位} [--unattended]   # 档位读 baseline versions.{V}.req_scale.tier

额外 prompt 输入：
- 输入变更摘要（含 PRD + 原型变更）+ 研发需求补充
- 当前原型代码（含改动）docs/prototype/{version}/code/（变更后版本，让 skill 重新提取页面布局/组件结构）
- 原详细设计/接口设计/数据库设计（基线，只读）

落盘（仅针对变更）：
- docs/design/detail/{version}/NN_<业务主题>.md（详细设计增量，如设计有变更）
- docs/design/detail/{version}/NN_<业务主题>.md（接口设计增量，如接口有变更）
- docs/design/detail/{version}/NN_<业务主题>.md（数据库设计增量，如表/字段有变更）
- docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql（如有 DDL 变更——遵循 Step 3.0 风格规则 + SKILL 命名规范；序号续在当前版本最大序号 +1；SQL 不加"补充"关键字）

回写：在目录 `00_索引.md` 登记本轮设计/接口/数据库增量行（类型=补充 + 生成时间），见 Step 2.4.5.5（`planning-5.md`）
事实清单：如 base / context-path / proxy / 端口有变 → 同步更新事实清单的「⚠️ 本次变更」表，触发 /sprint-design 的 Step 1.6 路径回检 + Step 1.6.5 消费者级联校验
```

> **原型变更的影响范围说明**：原型变更主要影响详细设计的"公共组件清单 / 模块结构 / 页面流转"段；接口字段如随原型表单字段调整也会有影响；数据库 DDL **通常不受原型变更影响**（除非原型新增了需要持久化的字段）

等待 `/sprint-design` 完成后再继续。

#### Step 2.4.3：调用 /sprint-plan

**fresh 模式**：

```
执行：/sprint-plan {version} --scale={档位} [--unattended]      # 档位 = Step 2.4.1.5 判定的 req_scale.tier（S|M|L）

该命令会调用 dev-execution-planner skill 生成研发执行计划
输出：docs/plans/{version}/00_索引.md + 01_研发执行计划.md（命令端 Step 2.4.4 归一 + 生成 00_索引）
```

**补充模式**（情况 B-2）：

```
执行：/sprint-plan {version} --supplement={NN} --scale={档位} [--unattended]   # 档位读 baseline versions.{V}.req_scale.tier

额外 prompt 输入：
- 输入变更摘要（含 PRD + 原型变更）+ 研发需求补充 + 设计补充（如有）
- 原 01_研发执行计划.md（基线，只读；历史裸 `00_研发执行计划.md` 兼容）

落盘：docs/plans/{version}/NN_<业务主题>.md（研发执行计划增量，仅列出新增 / 取消 / 时间调整的 Sprint 任务；未变 Sprint 不重复；文件名不带"补充"字眼）
回写：在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间），见 Step 2.4.5.5（`planning-5.md`）；任务分配矩阵中新增 / 变更的行用 🆕 / 🔄 / ❌ 标记
```

#### Step 2.4.3.5：★ 调用 /sprint-selftest 生成研发自测（方案 + 自测用例 + 测试环境与账号）

> 研发自测已从 `/sprint-plan` 抽出为独立命令（与 requirements/design/plan **对称**）。本步在执行计划生成后**显式调用**，是研发自测的**唯一生产步骤**——绝不省略、绝不“主动收尾”跳过（漏产会被 Step 2.4「三步落盘自检」硬门〔见 `planning-5.md`〕拦截）。研发自测的落盘核验 / 输出前硬门 / 目录归一均在 `/sprint-selftest` 内完成，命令端只编排。

**fresh 模式**：

```
执行：/sprint-selftest {version} --scale={档位} [--unattended]      # 档位 = Step 2.4.1.5 判定的 req_scale.tier（S|M|L）

输出：docs/testing/{version}/研发自测/00_索引.md + 01_研发自测方案.md + 02_ 用例…（多用例拆 03_<模块>）+ 01_测试环境与账号.md
（命令端 Step 2.4.4 对研发自测目录同样 dedup_prefix + gen_index 归一）
```

**补充模式**（情况 B-2）：

```
执行：/sprint-selftest {version} --supplement={NN} --scale={档位} [--unattended]   # 档位读 baseline versions.{V}.req_scale.tier

落盘：docs/testing/{version}/研发自测/NN_<业务主题>.md（研发自测用例增量，仅本次变更涉及的功能点；文件名不带“补充”字眼、补充身份记入 00_索引.md）
```

等待 `/sprint-selftest` 完成后再继续 Step 2.4.4。

