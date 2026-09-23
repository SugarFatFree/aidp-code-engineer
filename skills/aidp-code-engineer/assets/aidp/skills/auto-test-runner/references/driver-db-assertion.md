# DB 断言驱动（数据真值对账 · 可插拔）

> 端专有适配层文件。端无关的四原子能力契约、能力探测与优雅降级、扩展新端 SOP 见 `driver-adapters.md`。**本文件含端专有 API，属适配层——方法论层（`../SKILL.md` / `execution-methodology.md`）不得出现这些调用。**

---

## 二·补二、DB 断言驱动(数据真值对账 · 可插拔 assertion driver)

> **定位:** 这是**驱动适配层的一个可插拔适配器**,与 UI 四原子能力**并列**、互不替代。它不面向 UI,而是提供**「数据真值对账」**能力,专供 `[双源对账]` 用例执行期把**页面取值**与**数据库真值**比对。**两层解耦不受影响:方法论层只声明抽象需求「值级断言 / 数据真值对账」(见 execution-methodology.md「值级断言硬约束」与「不可视断言禁令的窄口径豁免」),具体 SQL / MCP 调用只落在本适配层。**

### 能力契约(端相关,只在此层出现)

| 能力 | 签名(语义) | 输入 | 输出 | 说明 |
| :- | :- | :- | :- | :- |
| **assertData** | `assertData(等价SQL, 页面取值) → 对账结果` | 用例「双源对账」段给出的等价 SQL + 从 `observe` 取到的页面值 | `{sqlValue, pageValue, match}` | 执行 SQL 取 DB 真值,与页面值比对;`match=false` 判该断言 fail |

- **数据源来源(二选一,可插拔)**:
  1. **复用会话已连的 DB MCP**——项目自行配置的数据库 MCP(如 `<db-mcp>`;服务已在会话内挂载时直接复用,免二次配置);
  2. **run-context `datasource` 传入的连接**(编排层前置提供:类型 / host / port / db / 账号,见 run-context-template「一、被测目标」)。
- **触发条件**:仅当用例带 `[双源对账]` 标记且「双源对账」段含等价 SQL 时启用;普通用例不走本驱动,一切断言仍走 UI `observe`(窄口径,避免不可视断言泛滥)。
- **前置数据编排复用**:第三项「前置数据编排」的 **SQL 造/删数途径**也复用本驱动(execute 型 SQL),与对账用同一数据源连接。

### 四能力映射(以项目自行配置的数据库 MCP `<db-mcp>` 为例)

- `assertData` → 调 DB MCP 的 `mcp__<db-mcp>__query`(读真值,如 `SELECT COUNT(*) / SELECT 金额 FROM ...`)取回结果集,与页面值逐项比对。
- 造/删数(前置编排 SQL 途径)→ 调 `mcp__<db-mcp>__execute`(`DELETE` / `INSERT` / `UPDATE`);同一数据库有多个环境变体时按 run-context `datasource.environment` 选对应服务名。
- **注意**:这些 `mcp__..._*` 工具名是**端专有 API**,**只允许出现在本适配层文件**;方法论层文档(execution-methodology / usecase-format / report-format)只写抽象的「DB 断言驱动 / 数据真值对账」,严禁写这些工具名(两层解耦 Critical)。

### 对账示例(伪代码,示意页面值 ⟷ SQL 真值)

```python
class DbAssertionDriver:
    def __init__(self, ds):            # ds = 已连 DB MCP 会话 或 run-context datasource
        self.ds = ds

    def assert_data(self, equiv_sql, page_value):
        rows = self.ds.query(equiv_sql)          # 端专有:DB MCP query,取 DB 真值
        sql_value = rows[0][0] if rows else None
        return {"sqlValue": sql_value, "pageValue": page_value,
                "match": str(sql_value) == str(page_value)}
```

> `match=false` → 该 `[双源对账]` 断言判 fail,结果 JSON 写 `db_assertion={pageValue, sqlValue, match}`(schema 见 report-format.md);页面看着对但库里不对(或反之)由此暴露。

### 归属校验探针(端专有落地 · 判定规则见 `execution-methodology.md` 第十一节)

> **在跑任何 `[双源对账]` 之前先做这一步。** 配了 `datasource` **不等于**它就是被测环境写入的库;用错库的对账**比不对账更危险**(SQL 值与页面值本就不该相等,结论要么假性全红、要么凑巧全绿,而 `match` 看上去笃定)。判定规则、四态结论与降级处置属端无关口径,只在方法论层第十一节;**本节只给端专有的 SQL / MCP 落地**。

| 级 | 端专有落地(以 DB MCP 为例) |
| :-: | :- |
| **P1 环境标识比对** | 不查库,读 run-context `datasource.environment` 与被测入口环境比对 |
| **P2 环境指纹比对** | 一条只读查询取环境指纹,如 `mcp__<db-mcp>__query` 执行 `SELECT config_value FROM sys_config WHERE config_key = 'env_name'`(或取回调域名 / 租户根等能唯一关联环境的配置行),与被测 URL 对应环境核对 |
| **P3 端到端回读探针** | 先经**被测环境**的 UI/接口造一条带唯一标识的数据(如名称含本轮 `round-{M}` 时间戳),再 `mcp__<db-mcp>__query` 执行 `SELECT COUNT(*) FROM {业务表} WHERE {唯一标识列} = '{本轮标识}'`;**查得到 → `verified`,查不到 → `mismatched`** |

- 探针结果写 `env-facts.json` 的 `datasourceOwnership` + `datasourceOwnershipSource`(受 `check_env_facts.py` 字段自动纳管约束,须逐字段标来源)。
- **探针本身失败 / 取不到结论 → 写 `unverified`,按 `mismatched` 同样处置(保守侧)**,不重试到死、不挂起。
- 上表 `mcp__..._*` 工具名是端专有 API,**只允许出现在本适配层文件**。

### 成熟度与降级

- **成熟度:预留可用(依赖会话已挂 DB MCP 或 run-context 给 datasource,且**归属校验结论为 `verified`**)**。**归属校验不是 `verified`(含 `mismatched`/`unverified`)时,本驱动整体停用**——相关用例降级为纯 UI 断言或标 `block(precondition-unmet)`,报告「遗留风险」写明「DB 归属校验未通过,双源对账不可用」;**绝不允许"先跑着、结论仅供参考"**。数据源都不可用 → 该 `[双源对账]` 用例整体标 `block(precondition-unmet)` + error 记「DB 断言驱动无可用数据源,需编排层提供 datasource 或挂载 DB MCP」,不硬失败、不挂起(与优雅降级一致);其 UI 部分仍可正常跑,只是缺 DB 真值对账。

---
