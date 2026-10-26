<!-- >>> SHARED-SEGMENT: flow-orchestration-doc >>> -->
# 编排层调用协议（QR 分级 / 移交清单 / 紧凑回传 / 阶段打点 / 分片输入裁剪）

> 本文件在 ux-logic-extractor / dev-logic-architect / dev-execution-planner / dev-manual-testcase
> 四个 SKILL 里各持一份、内容相同（SKILL 独立性原则）。可机检的部分全部由同 SKILL 的
> `scripts/qr_orchestration.py` 实现，⛔ 不手算、不手写格式。
>
> **★ 总约束：本文件描述的一切入参，非缺省值只由编排层（版本规划命令）传入；独立调用时 SKILL 不得自行切换。**
> 不传任何新入参时，产物与本协议上线前**逐字节等价**，QR 报告格式也不变。

---

## 一、入参

| 参数 | 取值 | 缺省 | 作用 |
| :- | :- | :- | :- |
| `qr_level` | `scripts` / `critical` / `full` | **不传**（= `full`，且 QR 报告按现状格式） | 决定语义 QR 审哪些维度；**显式传入任一值（含 `full`）即进入编排层模式**：QR 子 Agent 只回传紧凑 JSON（第四节） |

> dev-manual-testcase 另有 6 个入参（`plan_ref_mode` / `module_case_cap` / `matrix_scope` /
> `prd_presence_mode` / `prd_presence_table` / `module_kind`），只属于该 SKILL，入参表在它自己的 SKILL.md 约束区。

## 二、三档怎么派

**唯一依据：`quality-review-checklist.md` 顶部「维度成本与裁剪索引表」的 `等级` 与 `脚本可判` 两列。**
脚本读表时强制三条契约，任一不满足即 exit 2（SKILL 自身契约坏了）：`成本类别` ⇔ `脚本可判`（机器门 = 是、兼有 = 部分、语义 = 否）；
机器门脚本为 `—` 时不得为「是」；裁剪档 ∈ 全量 / 基线缩放 / Δ / —。
**条件维度**的唯一标记是维度名里的 `〔…〕` 括注或「（条件启用…）」——只有它们可以记 `na` 或在台账里不留行。
推导命令（QR 子 Agent 在步骤 0 之前先跑，输出不到 2 KB）：

```bash
python3 <SKILL_DIR>/scripts/qr_orchestration.py plan --qr-level critical
```

| 档 | 机器门（落盘后 bash 硬核回检） | 语义审 | 移交编排层 |
| :- | :- | :- | :- |
| `full` | 全量跑 | 全部维度，最多 3 轮 | 无 |
| `critical` | 全量跑 | `等级 = Critical` 的维度 | 非 Critical 且 `脚本可判 ≠ 是` 的维度 |
| `scripts` | 全量跑 | **仍含** `等级 = Critical` 且 `脚本可判 ≠ 是` 的维度（记 `escalated_dims`） | 同 `critical` |

- **机器门在任何档位都全量跑**，档位只裁语义审——与「QR 侧变更范围裁剪协议」第 1 条同一个理由。
- 非 Critical 且 `脚本可判 = 是` 的维度只有机器门、没有语义部分，三档都不需要移交。
- ⚠️ **与总约束的冲突与取舍**：需求里 `scripts` 档写的是「不派语义 QR 子 Agent」，同时总约束要求
  「不放松任何 Critical 判据、被跳过的只能是非 Critical 维度」。两条同时成立的唯一办法是：
  **Critical 维度永不移交**，脚本判不全的 Critical 维度在 `scripts` 档照样做语义审。
  按现有四份 checklist，所有 Critical 维度的 `脚本可判` 都不是「是」，所以 **`scripts` 与 `critical`
  两档实际审的维度相同**（`plan` 输出 `"equivalent_to":"critical"` 明示）。想让 `scripts` 真正省掉语义审，
  要么把某个 Critical 维度的判据**完整脚本化并通过变异测试**之后再改成 `脚本可判 = 是`（⛔ 只改表格那一格不算），
  要么改总约束；⛔ 不得在本文件或脚本里悄悄放行。
- **等级列只许比正文更严**：正文标题或正文子项写了 `(Critical…)` 的维度，等级列必为 Critical（由 `tests/test_qr_orchestration.py` 扫区段全文守）。
- **移交的维度不是「审过了」**：
  ① 不计入本 SKILL 的「通过终止」判定（终止 = 本档语义审范围内全部 ✅ + 机器门全过）；
  ② 编排层接手后**必须按移交 JSON 的 `delta_tier` 审**——标「全量」的维度（如依赖成环、TC-ID 全局唯一）⛔ 不得按 Δ 裁剪；
  ③ 编排层审完后用 `handoff --qr-level full --write` 清掉移交块（或重新生成产物）；块仍在 = 移交未结清。
- 条件维度（多文件 / Java 栈 / 第三方对接等）照旧按触发条件记 `N/A`；WebMCP 门控维度照旧按门控铁律不留行。

## 三、QR 移交清单（`qr_level ≠ full` 时必写）

写在产物目录的 `00_索引.md` 里、紧跟一级标题之后，两行，**人读行 + 机读 JSON 注释**：

```text
> QR 级别: critical；未审维度: [QR-04 示例维度甲, QR-07 示例维度乙]；移交: 编排层统一审计
<!-- AIDP-QR-HANDOFF: {"skill":"<本 SKILL 目录名>","qr_level":"critical","deferred_dims":[{"id":"QR-04","name":"示例维度甲","level":"Important","script_coverage":"否","delta_tier":"Δ"},{"id":"QR-07","name":"示例维度乙","level":"Important","script_coverage":"部分","delta_tier":"全量"}],"handoff_to":"编排层统一审计"} -->
```

（维度名为占位；真实内容由脚本生成，两行的维度必须一致。）

- **写入命令**（幂等；`full` 档会清掉旧块）：
  `python3 <SKILL_DIR>/scripts/qr_orchestration.py handoff --qr-level critical --write <产物目录>/00_索引.md`
  ⚠️ 这条由**主流程**在 QR 收敛后执行——它只写两行元信息、不是 QR 检查，不受「主流程禁止内联跑检查脚本」约束。
  写入跳过代码围栏里的示例行、保留原文件换行风格（CRLF 仍是 CRLF）。
- **人读行正则**（逐字）：
  `^> QR 级别: (scripts|critical)；未审维度: \[([^\]]*)\]；移交: 编排层统一审计\s*$`，
  条目按 `, ` 分隔，每条形如 `QR-NN 名称`（名称已去掉括注和逗号）。
- **机读行正则**：`^<!-- AIDP-QR-HANDOFF: (\{.*\}) -->\s*$`，JSON 字段固定为
  `skill / qr_level / deferred_dims[{id,name,level,script_coverage,delta_tier}] / handoff_to`。
- **编排层解析与校验**：`qr_orchestration.py parse-handoff <00_索引.md> --expect-level <派发时的档位>`（**必传**：
  缺清单与 `full` 档同形，不传就分不开）。它把清单与本 SKILL checklist 的推导结果**逐对象比对**（id / name / level /
  script_coverage / delta_tier 全部字段）：少登记、多登记、字段被改、把 Critical 维度写进去、两行不一致、
  不紧跟一级标题都判 exit 1——**移交清单不能靠自觉写全**。
- 维度编号 `QR-NN` = 该 SKILL checklist 里的维度/检查项编号补零到两位（`检查项 7` → `QR-07`）。
  ⛔ 不用 `D-NN`：dev-logic-architect 的待澄清/决策条目已占用 `D-NNN`，同写进 `00_索引.md` 必混。

## 四、QR 子 Agent 回传（编排层模式下只允许紧凑 JSON）

```json
{"skill":"<本 SKILL 目录名>","qr_level":"critical","round":1,
 "dims":[{"id":"QR-01","level":"Critical","verdict":"pass","findings_count":0,
          "scope":"基线缩放","gate_exit":{"check_a.py":0,"check_b.py":0},"readings":{"testcase_count":96}},
         {"id":"QR-03","level":"Critical","verdict":"fail","findings_count":2,"scope":"前滚","basis":"第 1 轮 QR 报告"},
         {"id":"QR-04","level":"Important","verdict":"deferred","findings_count":0}],
 "blocking":[{"dim":"QR-03","file":"03_用户管理.md","line":42,"summary":"SUITE-003 缺详细设计来源"}],
 "deferred_dims":["QR-04"]}
```

- 顶层**恰好**这 6 个字段，`dims` / `blocking` / `deferred_dims` 必须是数组；`round` 从 1 起。
- `dims[]` 必填 `id/level/verdict/findings_count`，可选 `scope/gate_exit/readings/basis`（「QR 执行台账」的紧凑形态）：
  `scope` ∈ 全量 / Δ / 前滚 / 基线缩放 / N/A，标「前滚」必须在 `basis` 写明依据的上一轮报告；
  `gate_exit` 是整数或 `{脚本名: 退出码}`（一个维度挂多个脚本时）；`readings` 是「名字 → 整数/布尔」。
- `verdict` ∈ `pass / fail / na / unverified / deferred`：
  `na` 只给条件维度；`pass` 不得与机器门 exit 1/2、`skipped:true`、采集量（`scanned_*` / `total_*` / `*_count`）为 0 同时出现——
  必查维度没跑记 `unverified`。`findings_count > 0` 而判 `pass` 只允许都是不阻断的 Important 发现。
- `dims[]` **一行不少**（未触发的条件维度由校验命令的 `--allow-missing QR-NN` 声明，非条件维度不接受）；`level` 必须等于 checklist 等级列。
- `deferred_dims` 必须等于 `plan` 推导出的移交集合，且这些维度的 `verdict` 必须是 `deferred`。
- Critical 维度判 `fail`/`unverified` 时 `blocking` 里至少一条；`summary` ≤ 120 字，任一字符串 ≤ 200 字，整体 ≤ 16 KB。
- ⛔ 禁止回传产物正文、脚本原始输出、长段落；需要证据时给 `file:line`。
- 校验：`python3 <SKILL_DIR>/scripts/qr_orchestration.py validate-result <result.json|-> --expect-level <档位>`。
  QR 子 Agent 回传前先自跑一次；主流程收到后再跑一次决定是否重派——它校验的是 ≤16 KB 的回传契约、输出一行，
  与 `handoff` 同属协议工具，不受「主流程禁止内联跑检查脚本」约束（那条管的是会挤占上下文的产物检查）。
- **不传 `qr_level` 时**（独立调用）QR 报告仍按 `flow-qr-dispatch.md` 的现状格式，本节不适用。

## 五、阶段打点 `[AIDP-STAGE]`

执行到以下边界时**输出一行**（只输出、不写计量文件；拿不到真实 token 数就不写，⛔ 不估算）：

```text
[AIDP-STAGE] {"skill":"<本 SKILL 目录名>","stage":"generate","shard":"用户管理","round":0,"event":"start","status":null}
```

| 边界 | stage | event | round | status |
| :- | :- | :- | :- | :- |
| 每个模块/分片生成开始 / 结束 | `generate` | `start` / `end` | 0 | start 恒 `null`；end 写 `pass`（落盘成功）/ `fail` |
| 第 N 轮 QR 开始 / 结束 | `qr` | `start` / `end` | N（从 1 起） | end 写本轮是否全部通过 |
| 第 N 轮修复开始 / 结束 | `fix` | `start` / `end` | N | end 写修复是否完成 |

- 字段**恰好且按序**为 `skill, stage, shard, round, event, status`；`shard` 无分片时为 `null`；JSON 紧凑无空格。
- 行正则：`^\[AIDP-STAGE\] (\{.*\})\s*$`。生成：`qr_orchestration.py stage --stage qr --event end --round 1 --status pass`；
  解析与校验：`qr_orchestration.py parse-stage <log|->`（格式错 exit 1；`unpaired` 列出只有 start 没有 end、或先 end 后 start 的边界）。
- 生成时强制：`generate` 的 round 必须是 0、`qr`/`fix` 从 1 起，`end` 必须写 `pass`/`fail`。
- 标记只出现在对话/日志输出里，**不写进任何产物文件**，因此不影响「产物逐字节等价」。

## 六、分片生成子 Agent 的输入裁剪（本 SKILL 按模块/分册/Phase 分片派生成子 Agent 时）

**切片规则**：每个生成子 Agent 只收到本片的
① 本片涉及的 REQ 条目全文（含 REQ 编号与所在文件路径 + 锚点）；
② 这些 REQ 在设计/上游文档里对应的章节片段（附 `文件路径#锚点` 与行号区间）；
③ 原型锚点（`原型文件路径#元素/行号`）；
④ **全局契约件全文**——全局错误码枚举、字典/枚举表、需求字段清单（表 A/B）、语义变更表 E/F、待澄清清单编号段。
④ 不裁剪：它们正是「全量」档维度要比对的东西，裁掉就重演「只看 Δ 内部永远自洽」。

**片外引用如何回读**：子 Agent 需要片外内容时，按片段附带的 `路径#锚点` / 行号区间用 Read 回读原文件，
⛔ 不凭记忆、不让主流程转述；溯源链接一律写**原文件**的相对路径与锚点（不是片段的临时位置），
所以引用溯源与不裁剪时完全相同、不降级。回读不到（锚点失效）时登记待澄清、⛔ 不臆造。

**主流程的义务**：派发时在 prompt 里列出本片 REQ 编号清单；QR 的「全量」档维度仍按全量核对（不受分片影响）。
<!-- <<< SHARED-SEGMENT: flow-orchestration-doc <<< -->
