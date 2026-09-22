# MySQL 方言设计约束

> 选型或既有库为 MySQL 系（MySQL / MariaDB）时加载。跨数据库通用的表结构设计原则（ER 关系图与外键、索引列 NOT NULL、审计字段四件套、字典枚举）见 `../SKILL.md`，此处只写 **MySQL 方言专有**约束。

---

## 一、`NULL != NULL` 语义（直接影响唯一索引设计）

MySQL 底层语义中 `NULL != NULL`（SQL 标准定义），后果：

1. **唯一索引允许重复 NULL 行**——本应唯一的列若可空，会放进多行 NULL，唯一约束形同虚设；
2. `WHERE col = NULL` 永远不成立，必须写 `IS NULL`；
3. `NOT IN (子查询)` 中只要子查询返回一个 NULL，整个结果为空。

> ✅ **设计约束**：**参与唯一索引 / 联合唯一索引的列一律 `NOT NULL`**（配默认值），这也是 `core-principles.md` 核心原则 8 / `quality-review-checklist.md` 检查项 21「索引列 NOT NULL 强制」Critical 维度在 MySQL 上的具体成因。

---

## 二、`VARCHAR(N)` 的 N 是字符数、不是字节数

MySQL `utf8mb4` 下 `VARCHAR(N)` 的 `N` 按**字符**计（一个中文 = 1 字符 = 最多 4 字节）。核心原则 13「文本字段长度冗余」要求按需求长度 **3×** 冗余时，**按字符数计**，不要误按字节换算。

---

## 三、InnoDB 单行总长度上限 65535 字节

- **单行所有列的总长度上限 65535 字节**（行格式 `DYNAMIC`/`COMPRESSED` 下 TEXT/BLOB 只占用少量指针空间，不计入该上限）。
- 设计宽表时若大量 `VARCHAR` 且 `utf8mb4`（每字符最多 4 字节），**很容易触顶导致建表失败**——`VARCHAR(500)` × 30 列即接近上限。
- ✅ **超长自由文本（备注、富文本、JSON 快照）改用 `TEXT`/`LONGTEXT`**，不要一味加大 `VARCHAR`。

---

## 四、字符集 / 排序规则 / 引擎沿用（历史 SQL 风格 Critical）

对既有库新增表时，`CHARACTER SET` / `COLLATE` / 引擎（`InnoDB`/`MyISAM`）**必须与历史 SQL 保持一致**，不得新表用 `utf8mb4_0900_ai_ci` 而历史是 `utf8mb4_general_ci`——排序规则不一致会导致 **JOIN 时报 `Illegal mix of collations`**。

```sql
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
```

---

## 核心原则 24：数据库级锁（P2）—— MySQL 侧识别清单

⚠️ **本节列出的全部写法都属 P2 档，默认不可用、必须经用户人为确认**（见检查项 32）。列在这里是为了**便于识别**，不是"可以用"。

| 写法 | 锁定范围 | 典型坑 |
| :- | :- | :- |
| `SELECT ... FOR UPDATE` | RR 隔离级下不止锁命中行，**还锁间隙(gap lock)** | 无索引命中会**退化成全表锁** |
| `SELECT ... LOCK IN SHARE MODE` / `FOR SHARE` | 共享行锁 | 两方各持 S 锁再升 X 锁 → **死锁** |
| `LOCK TABLES ... WRITE` | 整表 | 阻塞该表全部读写，与事务混用语义复杂 |
| `GET_LOCK(name, timeout)` | 命名锁（连接级） | **连接归还池后锁自动释放**，连接池场景语义不可靠 |

- **前置硬条件**：`FOR UPDATE` 的 `WHERE` **必须走索引**（否则锁全表），设计须显式写明命中的索引名。
- **必须写明**：锁定范围（行/间隙/表）、持锁时长与事务边界、`innodb_lock_wait_timeout` 取值、死锁重试策略、对连接池的影响。
- **⚠️ 乐观锁不属本节**：`UPDATE ... SET version = version + 1 WHERE version = ?` 是**无锁并发控制**，不需要确认门、仍推荐。

---

## 五、其它数据库方言

选型为**达梦 / Oracle / PostgreSQL / SQL Server** 等时，本文件不适用：`NULL` 语义、`VARCHAR` 计量单位（Oracle `VARCHAR2(N CHAR)` vs `N BYTE`）、行长上限、排序规则机制各不相同，须按所选库的官方约束重新核定，并同样遵守 `../SKILL.md` 的跨库通用原则（索引列 NOT NULL、外键约束、审计字段、历史风格沿用）。本目录**暂无这些方言的专有文件**——遇到时按通用原则设计并在文档中显式标注所用方言的差异点。
