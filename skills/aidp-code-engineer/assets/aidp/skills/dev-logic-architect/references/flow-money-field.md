# 货币金额字段设计规则(Critical)

> 本文件是 `SKILL.md` 核心原则 11「货币金额整数原则」的落地细则分片,按需 Read。
> **最小货币单位对照表**另见 [`currency-unit-reference.md`](./currency-unit-reference.md)(两文件配套:本文件讲怎么设计,那份是查表)。

## 💰 货币金额字段设计规则(Critical)

**所有货币/金额字段必须使用 64 位长整数,按当前国家/地区的最小货币单位存储。**

### 为什么必须用整数

1. **浮点精度**: `DECIMAL`/`FLOAT`/`DOUBLE` 在跨语言序列化、聚合运算、汇率折算时可能发生末位精度丢失,直接造成对账差异与资损
2. **跨语言一致**: 整数在 Java/Go/Python/JavaScript/Rust 等语言中行为一致,DECIMAL 在 JS(JSON Number)端无原生支持容易掉精度
3. **运算性能**: 整数加减乘除快于 DECIMAL
4. **业界共识**: Stripe、PayPal、Square、支付宝/微信支付 OpenAPI 均按最小货币单位(整数)传输金额
5. **审计/对账**: 整数累加和等于 BIGINT 范围内永不溢出常见业务场景(BIGINT 最大约 9.22×10^18,即使按"分"也支持约 9 千万亿元)

### 字段设计规范

**单币种业务(系统只服务单一国家/地区):**

> 示例中金额字段使用 `NOT NULL DEFAULT 0` 是常见做法(便于 SUM 聚合、避免 NULL 对账歧义),但**非强制**。是否 NOT NULL 由业务语义决定——如"退款金额"在未退款时用 NULL 表示"未发生"也是合理设计,只需在 COMMENT 中说明语义。

```sql
CREATE TABLE biz_order (
  id BIGINT PRIMARY KEY COMMENT '主键',
  order_no VARCHAR(32) NOT NULL COMMENT '订单号',
  total_amount BIGINT NOT NULL DEFAULT 0 COMMENT '订单总金额,单位:分(CNY)',
  paid_amount BIGINT NOT NULL DEFAULT 0 COMMENT '已支付金额,单位:分(CNY)',
  refund_amount BIGINT NOT NULL DEFAULT 0 COMMENT '退款金额,单位:分(CNY)',
  ...
) COMMENT '订单表(金额字段单位统一为分)';
```

**多币种业务(系统需支持多国/跨境):**

> 同上,金额字段是否 NOT NULL 由业务语义决定,示例仅展示常见做法。

```sql
CREATE TABLE biz_order (
  id BIGINT PRIMARY KEY COMMENT '主键',
  order_no VARCHAR(32) NOT NULL COMMENT '订单号',
  currency_code CHAR(3) NOT NULL COMMENT '币种(ISO 4217 三字母码,参考 A.4 > CurrencyCode)',
  total_amount BIGINT NOT NULL DEFAULT 0 COMMENT '订单总金额,单位:对应币种的最小单位(CNY=分/USD=cent/JPY=日元/KWD=fils)',
  exchange_rate BIGINT NOT NULL DEFAULT 1000000 COMMENT '兑换至本位币的汇率,×10^6 倍整数(如 7.123456 存为 7123456)',
  base_currency_amount BIGINT NOT NULL DEFAULT 0 COMMENT '折算为本位币(CNY)的金额,单位:分',
  ...
) COMMENT '订单表(多币种,金额单位随 currency_code 动态)';
```

> **汇率也避免小数**: 汇率字段同样建议用 BIGINT × 10^6 / 10^8 倍数存储,业务层除回得到展示汇率。

### 主要国家/地区最小货币单位对照表

> 📎 **完整对照表已拆分至** `references/currency-unit-reference.md`(含 3 张表 + 特殊小数位提醒 + 踩坑示例)。
> 生成详细设计时,Agent 应读取该文件获取目标币种的小数位指数。

**快速参考(常见特殊币种):**

| 类型 | 货币 | 小数位 | 存储示例(100 主币) |
| :- | :- | :-: | :- |
| 0 位(主币=最小单位) | JPY / KRW / VND / HUF / ISK / CLP | 0 | `100`(÷1) |
| 2 位(常规) | CNY / USD / EUR / GBP / INR | 2 | `10000`(÷100) |
| 3 位(中东第纳尔系) | KWD / BHD / JOD / OMR | 3 | `100000`(÷1000) |

> **关于 IDR(印尼盾)**: ISO 4217 标 2 位(主币 = 100 sen),但 sen 实务已不流通,部分系统按 0 位处理;接入印尼业务前需与对接方明确按 ISO(×100)还是按实务(×1)存储,并在 A.4 `CurrencyCode` 字典中显式标注。

> **踩坑示例**: 用户输入 100 科威特第纳尔,**正确**存储为 `100000`(单位 fils);若按常规 ×100 处理则少存 10 倍,直接造成 90% 资损。

### 应用层与接口层约定

1. **数据库存整数,接口传整数**: 数据库 BIGINT、对外 API 响应字段也是整数(避免 JSON 浮点),并在字段说明文档中注明"单位:对应币种最小单位"
2. **展示层负责还原**: 前端/报表/导出文件按 `currency_code` 查询小数位指数还原为人类可读金额(中国 `1000` → `10.00 元`、日本 `1000` → `1000 yen`、科威特 `1000` → `1.000 KWD`)
3. **金额输入校验**: 用户输入"10.50 元"时,前端 ×100 = 1050 后再传后端;后端再次校验"是否整数 ≥ 0",拒绝任何非整数请求
4. **跨币种汇总**: 必须先按汇率折算为同一本位币(整数 × 整数汇率 / 10^6)再汇总,避免不同币种的整数直接相加
5. **A.4 字典对照**: 详细设计 A.4 章节应定义 `CurrencyCode` 字典(枚举 ISO 4217 三字母码 + 中文名 + 最小单位名 + 小数位指数),供应用层查询
6. **JSON 传输精度风险(JS Number 上限)**: BIGINT 在 JSON 序列化到 JavaScript 时,`Number` 安全整数上限为 `2^53 - 1 ≈ 9.007×10^15`(按"分"约 90 万亿元)。**日常交易金额远低于此上限**,可直接用 `integer` 传输;但**财务汇总/历史累计/高面值高通胀币种(VND/IDR/IRR 等,名义金额位数大)**字段可能超限,API 层必须用 `string` 类型传输金额(后端 `@JsonSerialize(using = ToStringSerializer.class)` 或前端 `BigInt`),并在 B.2 接口契约中明确字段类型为 `string` 而非 `integer`

### 唯一允许的例外

**1. 已有项目保持现有约定(最高优先级):**

若项目已有正式代码且金额字段已使用 `DECIMAL` 或其他类型,**新增功能/表的金额字段应与项目现有约定保持一致**,不强行迁移为 BIGINT。理由:
- 同一项目内金额字段类型不一致会导致计算逻辑混乱、对账困难
- 迁移已有字段涉及数据迁移、接口变更、前端适配,风险远大于收益
- 在设计文档中标注"沿用项目现有金额字段约定(`DECIMAL(M,N)` / `BIGINT` / ...),理由:与已有表 `xxx.amount` 保持一致"即可

**2. 新项目/空仓库(整数原则生效):**

仅在以下场景**可以**降级使用 DECIMAL,且**必须**在设计中显式标注理由:

- 与无法改造的遗留系统/外部银行接口对接,对方只接受 DECIMAL 金额
- 仅用于"展示快照"的统计报表表(非交易表),且业务接受小数末位四舍五入

降级时也必须使用 `DECIMAL(M,N)` 显式指定精度(如 `DECIMAL(18,2)`),**严禁** `FLOAT` / `DOUBLE`。

---
