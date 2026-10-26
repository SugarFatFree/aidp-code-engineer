# 维护者说明:关键约定的根因

> 本文件只给**维护本 SKILL 的人**看,执行用例时不必读。`SKILL.md` 正文只写现行行为,
> 「为什么这样定、改回去会怎样」集中记在这里,避免正文堆积历史对比。

## 1. 执行子 Agent 默认只读精简契约

- **根因**:若要求每个执行子 Agent 都先整份读 `SKILL.md` + `execution-methodology.md` + `driver-*.md` + `report-format.md` 四份,一轮 5 个 Agent 就是 4× 重复加载(实测 2.11M tokens / 479 次工具调用),而绝大多数用例只用到其中一小部分。
- **现行口径**:默认只读 `references/execution-contract-lite.md`,判不准时按其索引翻全文。收的是加载量、不是强制度。
- **守护**:精简契约天然是「同一判据两份实现」的风险源,故枚举与必填集的信源仍在 `scripts/check_result.py` 与 `report-format.md`,由 `tests/test_execution_contract_lite.py` 逐项比对并守体量上限。

## 2. 约束编号必须连同标题关键词一起引用

- **根因**:编号在增删条目时整体位移,位移后的错误引用两侧都仍「在范围内」。实际项目中出现过引用第 9 条、实指第 10 条的错位,长期无人告警。
- **现行口径**:约束固定为 `### 约束 N:<标题>` 形态,引用处必须带标题关键词。

## 3. 单条耗时三件套

- **根因**:没有逐条 `started_at` / `finished_at` / `elapsed_ms` 时,「一条用例占整轮 25%」这类结论只能靠 evidence 文件 mtime 手工反推,而那只对产出了多个 evidence 的用例有效,非常容易整条漏掉。
- **现行口径**:每条结果必带三件套;批次均摊值须标 `elapsed_is_amortized` + `batch_id`。

## 4. `application_mcp.implementation_kind` 与驱动来源

- **非 Web 合法值为 `app-native` / `bridge`**:与声明侧(调用方 `client_mcp` 声明、详细设计)同一套取值。旧值 `app-service` 是本 SKILL 早期文档写过的取值,既有结果可能如实带着它,故按 `app-native` 兼容解析并报 Important(`application_mcp_implementation_kind_legacy`),不判 Critical——判死会惩罚按旧文档如实登记的结果。
- **四态 `source` 不得是测试驱动**(`application_mcp_driver_as_evidence`,Critical):Appium / CDP / chrome-devtools 等驱动可用只说明「能操控客户端」,不说明「应用自己暴露了 MCP 业务能力」。ASCII 标记按「非字母数字」词边界匹配,避免 `cdp` 误伤 `cdpath` 这类无关单词。`chrome[\s_-]?devtools` 同时认空格 / 连写 / 下划线三种写法——只认连字符时「Chrome DevTools MCP 列出」这种最自然的写法会漏判(假绿)。`implementation_evidence` 纳入同一判据(以「未取到」开头的如实未交付说明除外,否则如实标注反而换来告警)。
- **守护**:`tests/test_application_mcp_kind_and_driver_source.py`(阳性 / 阴性 / 词边界 / 旧值兼容)。

## 5. 报告章节口径与 2.7 耗时分布

- **根因**:报告旧称「六章节」,指的是必备内容块数而非顶层一级标题数,按顶层标题去核会得到假不通过;2.7 耗时分布后来加入必备集(块数由 6 变 7),无耗时数据时也须照脚本输出写「本轮 N 条全部未采集」,否则空表 / 缺节会被读成「都很快」。
- **现行口径**:以 `quality-review-checklist.md` 维度 7 的「章节口径」为准(3 大章 / 7 个必备内容块)。

## 6. 环境探针档案的 `verdict` / `事实性质` 硬要求

- **根因**:档案早先只写了「冲突时改写为『已失效 + 新结论』」,但没有任何机器门确保这件事做了。实测某行带 ⛔⛔ 的「主测账号口令失效」**错误结论**按契约被注入执行子 Agent 的 prompt,导致上一轮 31 条登录态用例集体 block。绝对值基线(如「列表共 5 条」)则会因上游并发改动在测试窗口内过期,制造假性失败。
- **现行口径**:每条必填 `verified_at` + `verdict` + `事实性质`,注入前过滤 `superseded`(档案里留痕不删);只记不变量、不写固定数值基线。机检 `scripts/check_probe_archive.py`。
