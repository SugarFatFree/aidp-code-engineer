# 执行契约(精简版) — 执行子 Agent 默认只读这一份

> **为什么有这一份:** 执行子 Agent 拿不到 Skill 工具,只能靠 `Read`。派
> SKILL.md + execution-methodology.md + driver-*.md + report-format.md 四份全文 ⇒ 一轮 5 个
> Agent = **4× 重复加载**(实测 **2.11M tokens / 479 次工具调用**),而多数用例只用到其中一小部分。
>
> ⚠️ **收的是加载量,不是强制度** —— 本文件每一条都是硬要求;判不准就按第五节索引去读,⛔ 不自行发挥。
> ⚠️ **本文件不是判据信源**:枚举以 `scripts/check_result.py` 常量为准,字段语义以
> `references/report-format.md` + `assets/result-schema.json` 为准,冲突时以它们为准。
> `{{AIDP_HOME}}/scripts/tests/test_execution_contract_lite.py` 逐枚举比对,漏同步即红 ——
> 这是它敢存在的前提(否则就是本仓库最高频的「同一判据两份实现」)。

---

## 一、三条红线

1. **绝不改业务代码、绝不修复缺陷。** 发现缺陷只判定 + 记录,标 `fail`/`block` 后**继续测完**;
   `self-heal` 只恢复会话/登录/前置数据的**运行态**。
2. **取不到的事实写「未取到 + 原因」,⛔ 不写一个像样的默认值。**
3. **前置不满足记 `block`,⛔ 不得换个变体路径凑一个 `pass`** —— 变体路径的正确返回若恰好等于
   原用例的正确返回,缺陷会被断言「接住」(下游实测,直到终审才暴露)。
   **未执行的步骤不得随套件计入通过数。**

## 二、进度状态机(`tasks.md` 是唯一真相)

`[ ]` 待执行 / `[>]` 执行中 / `[√]` 已完成(pass) / `[!]` 阻塞或失败(fail/block)。

- 批量前整模块 `[ ]`→`[>]`,执行完据结果 `[>]`→`[√]` 或 `[>]`→`[!]`。
- 续跑用 `tasks_state.py resume`,已 `[√]` 跳过;出报告前必须**无 `[ ]`/`[>]` 残留**。
- ⚠️ 跳过**仅限同一 build 内中断恢复**。**新 build = 新回归轮**:`init` 全新 tasks.md、
  全部回初始态、**全量重跑** —— 只复验被修用例会漏同源缺陷。

## 三、四态口径(`status`)

| 值 | 用在什么时候 |
| :- | :- |
| `pass` | 全部预期通过 |
| `fail` | 关键预期**验证失败**(产品缺陷) |
| `block` | 重试到顶仍失败 / 前置不满足 / 驱动缺失 / 网络不可用,**原因由 `block_reason` 承载** |
| `na` | 本轮不适用,须在 `note`/`na_reason`/`error` 之一写明原因;不计入通过率分子与分母 |

`block_reason` 枚举(**只能用这些,⛔ 不自造**):`driver-missing` / `driver-hung` /
`precondition-unmet` / `network-error` / `env-unavailable` / `account-invalid` /
`retry-exhausted` / `webmcp-driver-too-old` / `webmcp-driver-version-unknown`。

- ⚠️ `precondition-unmet` **只有**前置探测 `precondition_probe.status=unmet` 才能用;探测本身
  出错须按网络/环境错误归因,**不得伪装成数据缺位**。
- 失败分级**不中断**:重试 ≤3 → 仍失败则 `block` + 证据 → **继续下一条**。

## 四、产物契约 `results/{TC-ID}.json`

必填:`case_id` / `suite` / `test_name` / `priority` / `client` / `driver` / `execution_mode` /
`status` / `is_reverse` / `error` / `evidence` / `runtimeErrors` / `retries` / `started_at` /
`finished_at` / `elapsed_ms`。

- `entry_kind`:缺省 `case`;自由巡检项必须填 `free-scan`(**不计入用例统计** —— 混进 `total`
  会让「巡检页越多通过率越好看」)。
  ⚠️ **`free-scan` 豁免 `suite` / `priority` / `execution_mode` 三个必填**(它不属任何套件、
  没有优先级、也没有执行模式分级);⛔ **尤其不要给它填 `execution_mode: verified`** ——
  那样 `pass` 且无 evidence 会触发 **C4 Critical**。
- `execution_mode` ∈ `direct`/`verified`/`self-heal`。后两者的 `pass` **必须有完整证据**;
  `direct` 的 `pass` 至少一条**轻量事实**(实际值/命中文案/列表计数/产物路径)。
- `evidence[]` = `{step, summary, artifact}`;`artifact` 必须是 capture **实际返回**的当前轮次
  `round-{M}/evidence` **相对路径**,文件存在且非 0 字节,截图名 `{case_id}-step{step}`。
  ⛔ 不得按 TC-ID 猜扩展名。
- `mechanism` ∈ `dom`/`webmcp`/`app-mcp`/`mixed`。⚠️ **未填 ≠ 已确认是 dom**(报告单列「未声明」)。
  ⛔ **`[还原度]` 及一切视觉/布局/样式断言禁填 `webmcp`** —— 它读的是声明的能力,不是渲染结果。
- **耗时来源**:`elapsed_ms` 若是批次窗口均摊值(「窗口 ÷ N」,批量执行下这是常态),必须把
  `elapsed_is_amortized` 填 `true` 并给出 `batch_id`(可选 `batch_elapsed_ms`,填了会被 I15 核)。⚠️ 写进 `note` **不算** —— 聚合器不读 `note`,
  会把它当逐条真值排名,产出「某条用例耗时 28 分钟」这种**假事实**(下游实测)。

**落盘后必跑:** `python3 <SKILL_DIR>/scripts/check_result.py <round_dir>/results --json`

## 五、判不准时翻哪一页

| 情形 | 去读 |
| :- | :- |
| 字段语义 / 报告某节怎么填 | `report-format.md` |
| 批量调度、感知-执行-校验-决策闭环、环境准备取证、双源对账归属 | `execution-methodology.md` |
| 驱动具体写法、能力探测与降级 | `driver-adapters.md` + 本端 `driver-<端>.md` |
| 用例文件怎么解析、断言 DSL | `usecase-format.md` |
| 应用自有 MCP 业务工具用例 | `driver-client-mcp.md`(Web+WebMCP 另见 `driver-web-webmcp.md`) |
| `[双源对账]` / DB 断言 | `driver-db-assertion.md` |

⚠️ **判不准就去读,⛔ 不要猜。** 本文件只保证你知道**哪些是硬要求**、**产物长什么样**、
以及**不懂时该翻哪一页**。
