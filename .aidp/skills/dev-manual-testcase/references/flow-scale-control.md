# 编排层规模控制入参（plan_ref_mode / module_case_cap / matrix_scope / prd_presence_mode / module_kind）

> 入参总表在 `SKILL.md` 约束 13「编排层调用入参」。**全部入参缺省值 = 现状**；非缺省值只由编排层传入，独立调用时不要自行切换。
> 通用部分（`qr_level`、移交清单、紧凑回传、`[AIDP-STAGE]` 打点、分片输入裁剪）见 [`flow-orchestration.md`](./flow-orchestration.md)。
>
> **不放松的东西（任何参数组合都成立）**：PRD 功规点 100% 覆盖（维度 1）、上游溯源（维度 13）、字段核对（维度 17）、
> 自测方案引用闭环（维度 16）、反向占比 ≥40%、P0/P1 覆盖。下面五项只改变**产物怎么写、写多少**，不改变这些判据。

---

## 一、`plan_ref_mode = required | deferred`（自测用例与执行计划解耦）

**用途**：编排层让「执行计划」与「自测用例」并行生成。`deferred` 时本 SKILL **不读研发执行计划、不要求它存在**，
用例只锚定 REQ 编号（以及原型/设计锚点）。

**占位符语法**：`⟨PLAN-REF:<REQ 编号>⟩`
- 尖括号是 U+27E8 / U+27E9（`⟨` `⟩`），⛔ 不是 `<` `>`，避免与 HTML/占位模板混淆；
- REQ 编号须满足共享段 `req-id-pattern`（`REQ-004` 与 `REQ-V0.17.0-004` 两种形态都认，按字符串处理）。

**写法**（套件头部 S4 行；S1 里列了几条 REQ 就写几个，用「、」分隔，顺序随 S1）：

```text
> **PRD 来源**: [REQ-004 用户管理](../requirements/V1/研发需求/01_PRD.md#REQ-004)、[REQ-007 角色](../requirements/V1/研发需求/01_PRD.md#REQ-007)
> **研发执行计划来源**: ⟨PLAN-REF:REQ-004⟩、⟨PLAN-REF:REQ-007⟩
```

**替换规则**（编排层在计划生成后执行，全有或全无）：

```bash
python3 <SKILL_DIR>/scripts/resolve_plan_refs.py <用例目录> --map plan_refs.json
# plan_refs.json: {"REQ-004": {"label": "Sprint-012 T-012-03", "href": "../plans/V1/01_研发执行计划.md#T-012-03"}}
```

每个 `⟨PLAN-REF:REQ-004⟩` → `[Sprint-012 T-012-03](../plans/V1/01_研发执行计划.md#T-012-03)`；
`label` 必须形如 `Sprint-NNN T-NNN-NN`，`href` 必须是指向 `.md` 的相对路径；任一占位符找不到映射 → 一个文件都不写、exit 1。

**两种形态都要过硬门**：

| 时点 | 命令 | 判据 |
| :- | :- | :- |
| 替换前 | `check_suite_upstream.py <目录> --plan-ref-mode deferred` | S4 只校验：占位符存在、编号合法、与 S1 的 REQ 一一对应、⛔ 不得已填 Sprint/链接 |
| 替换前 | `check_testcase_format.py <目录>` | 照常（占位符在套件头部，不在步骤表内） |
| 替换后 | `check_suite_upstream.py <目录>`（缺省 required） | 与现状完全一致：S4 是链接、链接合规 |
| 替换后 | `check_testcase_format.py <目录>` | 照常 |

- ⚠️ 缺省 `required` 模式下，**全文任意位置**残留 `⟨PLAN-REF:…⟩`（代码围栏与行内代码里的示例除外）一律判不通过——含「同一行已替换一半」与「写在 N/A 行里」两种形态，编排层漏跑替换不会被放过。
- **增量模式（模式 B，以执行计划为范围裁剪）不受影响，恒为 `required`**：它的范围就是计划里的 Task，读不到计划就无法裁剪。
  编排层在模式 B 传了 `deferred` 时按 `required` 处理，并在 `00_索引.md` 元信息里注明。
- 维度 6（执行计划覆盖）只在模式 B 存在，故不受 `deferred` 影响；维度 13 的 S4 子项按上表改读口径，S0/S1/S3 不变。

## 二、`module_case_cap`（L 档每模块用例上限）

- 只对 **L 档**生效（S/M 档是整轮合计基线，另有口径）；编排层典型值 30。不传 = 不设上限（现状）。
- 超出时**只合并或删减 P2**：同一筛选条件的组合合并为一条参数化用例、重复路径的 P2 删去；⛔ 不删 P0/P1、不删反向用例。
  反向占比 ≥40% 与 P0/P1 覆盖不受上限约束——**P2 全删仍超上限**时上限让位（脚本记 `over_p0p1_only`）。
- 统计摘要**必须**写一行（未删减写 0 条）：
  `> 被合并/删减的 P2: N 条 —— 理由: <一句话>`（理由不可省，缺理由视同未声明）
- 机检：`check_case_stats.py <目录> --scale L --module-case-cap 30 --json` → 每个文件的 `cap_check`
  `{cap,total,p2,status: within|over|over_p0p1_only, p2_trimmed_declared}`；超上限与缺声明都是 **Important**（warning，不占退出码）。
- ⚠️ 传了上限时，维度 19 的 L 档「每模块基线（简单 30-60）」下限按 `min(基线下限, 上限)` 读，⛔ 不得因「低于 30」再报基线不足。

## 三、`matrix_scope = all | p0`（覆盖矩阵展开范围）

- `all`（缺省，现状）：每条 REQ 都逐维展开正向 9 维 + 反向 12 维。
- `p0`：**只对 P0 需求逐维展开 21 维**；P1/P2 需求只写一行：
  `> 覆盖矩阵(P1/P2 汇总): 适用维度 F1,F2,F3,R1,R5 —— 不适用理由汇总: 无状态流转(F7/R9)、无并发写(R10)…`
- 维度 18 的通过判据随之调整：P0 需求逐维确认（不适用须标注）照旧；P1/P2 需求核「适用维度清单 + 不适用理由汇总」是否存在、
  适用维度是否都有用例。⛔ 反向占比 ≥40% 不变；BVA/等价类/状态机/并发四法对 P0 照旧全量套用。

## 四、`prd_presence_mode = cases | table`（`[PRD存在性]` 用例族）

- `cases`（缺省，现状）：产品 PRD 每个可测存在性条目一条 `[PRD存在性]` 用例（`flow-step5-coverage.md` 第五步之一）。
- `table`：编排层用确定性脚本产出「PRD 行 → 研发需求对账表」，路径由 `prd_presence_table` 传入；本 SKILL **只对表中「未承接」行**
  生成补充用例，「已承接」行不再逐条写用例（它们已由研发需求 → 用例的正常链路覆盖，编排层的 PRD 行级反向覆盖审计查的是同一件事）。
- **对账表契约**（四列，列名固定，编排层脚本产出）：

  ```text
  | PRD 行号 | PRD 原文 | 承接 REQ | 状态 |
  | :- | :- | :- | :- |
  | L30 | 详情页须展示「创建人」 | — | 未承接 |
  ```

  `状态` ∈ `已承接` / `未承接`；`PRD 行号` 是补充用例的引用键。
- **补充用例写法**：**标题**带 `[PRD存在性]`，并写 `> **PRD 行号**: L30`（一条用例承接多行时用「、」分隔）。脚本只从标题认标记、只从「PRD 行号」字段取行号（行号须独立成词，`L300` 不算 `L30`）——正文里顺带提到「原型 L30 附近」不算承接。PRD 原文含 `|` 时按 GFM 转义为 `\|`，脚本按转义感知切列。
- 机检：`check_case_stats.py <目录> --prd-presence-table <表路径> --json` → `prd_presence {rows, unaccepted, covered, uncovered_rows}`；
  有未覆盖行 **exit 1**（维度 1 的 PRD 原文存在性子条不通过）；表解析不出、缺列、状态值非法一律 `{error}` + exit 1（⛔ 不当成 0 行通过）。
- 没传表路径却传了 `table` → 按 `cases` 处理，并在报告注明「未收到对账表」。

## 五、`module_kind = interactive | non_interactive | auto`（非交互模块简化模板）

**识别规则**：
- `interactive`（缺省）：全部按页面模板（现状）。⚠️ 此时 `[非交互]` 标记**不生效**：三个硬门照页面模板判，并报 Important `noninteractive_unauthorized`。
- `non_interactive`：本次调用的全部模块按非交互模板。
- `auto`：逐模块读详细设计里该模块的 **`模块类型`** 字段（形如 `> **模块类型**: 批处理`）；值为
  `迁移工具 / 数据迁移 / 数据脚本 / 批处理 / 定时任务 / CLI / 命令行工具` 之一 → 非交互，其余或字段缺失 → 页面模板。
  ⛔ 不根据模块名、不根据「页面少」自行推断。

**模板**（套件与用例都带 `[非交互]` 标记；不写页面步骤表、不生成通用还原度套件）：

```markdown
## 套件 SUITE-MIG-001 [非交互]: 数据迁移工具
> **自测方案章节**: …  > **PRD 来源**: …  > **原型来源**: N/A(纯后端)  > **详细设计来源**: …  > **研发执行计划来源**: …

#### 入口流程 (Suite Setup)
- 运行环境: 工作目录 `tools/migrate/`,环境变量 `DB_URL` 指向测试库

#### TC-MIG-001: [非交互] 全量迁移成功
> **优先级**: P0 | **类型**: 正向

**命令**: `./bin/migrate --from v1 --to v2 --report out/report.json`
**前置数据**: 源库 `user_v1` 表 120 行(含 3 行软删除)
**预期退出码**: 0
**输出断言**:
- `out/report.json` 中 `migrated` = 117
- 标准输出末行含「迁移完成」
```

> **硬门授权**：`check_testcase_format.py` / `check_testcase_suite.py` / `check_fidelity_suite.py` 须带 `--module-kind non_interactive`（或 `auto`）才认 `[非交互]`；缺省 `interactive` 不认。
> `auto` 时脚本认标记，「标记是否与设计的 `模块类型` 字段一致」由 QR 子 Agent 逐模块核（维度 7）。

| 硬门 | 对 `[非交互]` 的处理（已授权时） |
| :- | :- |
| `check_testcase_format.py` | 四段（命令 / 前置数据 / 预期退出码 / 输出断言）缺任一段、退出码不是整数、命令里绕道调接口（curl / wget / `requests.*` / `fetch(` / 大写 `POST /x` 等；CLI 子命令 `get /a` 不算）→ **Critical**；同时写了步骤表则步骤表照常校验 |
| `check_testcase_suite.py` | Suite Setup 仍必须有且只有一个，内容须写明运行环境 / 工作目录 / 环境变量（⛔「准备」「配置」这类泛词不算），不要求打开浏览器与登录 |
| `check_fidelity_suite.py` | `[非交互]` 的用例/套件不算 UI 用例信号；混有页面用例时页面部分照常要求覆盖表 |
| `check_case_stats.py` / `check_suite_upstream.py` | 不区分，照常（反向占比、统计摘要、6 行溯源都适用） |

- ⚠️ 标记本身**不豁免任何检查**：贴了 `[非交互]` 却缺四段 → Critical，不会因此逃过「缺测试步骤」。
- ⛔ 非交互模块**不要**写「本轮无 UI 页面用例」声明来关掉还原度检查——那条声明作用于整个目录，混着页面模块时等于假绿。
- 反向用例照样 ≥40%：参数缺失 / 非法参数 / 源数据为空 / 目标已存在 / 中途失败可重入 / 权限不足等，断言落在退出码与报告上。

## 六、对 QR 判据的影响（只在传了非缺省值时生效）

| 入参 | 受影响维度 | 怎么读 |
| :- | :- | :- |
| `plan_ref_mode=deferred` | 13（S4 子项） | 按第一节表格；S0/S1/S3 100% 不变 |
| `module_case_cap` | 19 | 超上限 / 缺 P2 删减声明 = Important；基线下限按第二节读 |
| `matrix_scope=p0` | 18 | 按第三节；反向占比与 P0 逐维确认不变 |
| `prd_presence_mode=table` | 1（PRD 原文存在性子条） | 只核「未承接」行是否都有补充用例 |
| `module_kind` | 7 / 8 / 21 | 按第五节表格 |

QR 派发时把这些入参原样告诉 QR 子 Agent，并在步骤 0 的命令上带对应参数（`flow-qr-dispatch.md`「编排层模式」小节）。
