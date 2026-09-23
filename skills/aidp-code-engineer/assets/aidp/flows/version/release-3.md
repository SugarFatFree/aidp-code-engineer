# /version · 版本发布流程详情 — 分片 3/9

> 本片覆盖：**Step 3.3.7 部署产物整理（含 3.3.7.1–3.3.7.6）**。
> 完整分片清单见 `{{AIDP_HOME}}/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
### Step 3.3.7：★ 本版本部署产物整理完善（`docs/deployment/{version}/` 发布前优化整理）

**目标**：发布前对整个 `docs/deployment/{version}/` 部署目录做**优化、整理、完善**——不止 SQL，覆盖 `sql/增量/` + `部署流程/` + `配置文件/` + `{version}-deployment-checklist.md` 等全部部署产物，产出一份运维可无脑照做、内部自洽一致的发布态部署资产。本步**分两部分**：

- **A 部分（SQL 整理归档）**：把 `sql/增量/` 内**分散累积**的 SQL 文件（多 Sprint / bugfix 各自追加）**整合重组**为按 DDL / DML 拆分的归档结构，只保留整理后的文件、原始零散文件 `git rm`（git 历史可追溯）。详见 3.3.7.1~3.3.7.6。
- **B 部分（部署目录其余产物完善 + 跨文档一致性）**：完善 `部署流程/部署流程.md`、`配置文件/增量/配置项清单.md`、`{version}-deployment-checklist.md`，并把它们对 SQL 文件名的引用**对齐到 A 部分整理后的实际文件名**。详见 3.3.7.7。
- **C 部分（跨版本工具目录 `docs/deployment/tools/` 整理）**：轻量整理跨版本运维 / 一次性工具归档目录——README 索引对齐刷新 + 清理 `__pycache__` 等构建产物 + 未归类文件归位提示。**★ 独立于 `{version}/` 是否存在**（tools/ 非版本隔离），只做「识别 + 规范位置 + README 索引」、不校验工具 SQL 内容。详见 3.3.7.8。

**执行时机**：Step 3.3.5（`release-2.md`；版本更新日志）之后、Step 3.4.1（`release-7.md`；发布提交）之前。先跑 A（SQL 整理，确定最终文件名）再跑 B（其余产物完善 + 引用对齐）——**★ 但 B / C 独立于 A：即使 A 无 SQL 可重组（SQL 已规范），B（完善 + 四文档一致性核对）与 C（tools/ 整理）仍强制跑完**，不被 A 的跳过短路（见 3.3.7.1 解耦铁律）。

#### Step 3.3.7.1：A 部分跳过条件（★ 只跳过 A 部分 SQL 重组；B / C 独立照常执行）

> **★ 解耦铁律**：本跳过条件**仅决定 A 部分（SQL 重组）是否执行**——**绝不 `exit` 整个 3.3.7**。SQL 已规范 / 无需重组时 A 部分空跑（`SKIP_A=1`），但 **B 部分（部署流程/配置清单/checklist 完善 + 四文档一致性核对）与 C 部分（tools/ 整理）必须照常跑完**。⛔ 「SQL 无重组即 `exit 0`」会连带把 B/C 静默跳过。

```bash
SQL_DIR="docs/deployment/{version}/sql/增量"
SKIP_A=0
# A 部分（SQL 重组）跳过判定 —— 只置 SKIP_A 标志，【绝不 exit】，B/C 后续独立执行
[ ! -d "$SQL_DIR" ] && echo "A 部分跳过：无 $SQL_DIR（不影响 B/C）" && SKIP_A=1
if [ "$SKIP_A" = 0 ]; then
  NON_ROLLBACK_COUNT=$(ls "$SQL_DIR"/*.sql 2>/dev/null | grep -v "99_回滚脚本.sql$" | wc -l)
  [ "$NON_ROLLBACK_COUNT" -eq 0 ] && echo "A 部分跳过：无可整理 SQL（不影响 B/C）" && SKIP_A=1
fi
# SKIP_A=1 → 跳过 3.3.7.2~3.3.7.6（A 部分 SQL 重组）；无论 A 是否跳过，都继续 3.3.7.7（B 部分，强制）+ 3.3.7.8（C 部分）
```

> 下方 3.3.7.2~3.3.7.6（A 部分 SQL 重组）仅在 `SKIP_A=0` 时执行；`SKIP_A=1` 直接跳到 3.3.7.7。

#### Step 3.3.7.2：整理规则

| 规则 | 内容 |
|------|------|
| **范围** | 仅整理 `docs/deployment/{version}/sql/增量/` 下的 `.sql` 文件；**不动** `sql/全量/`（全量轨由 Step 3.3.7.9 按最新代码重算，不参与增量重组）、**不动**任何 `docs/deployment/{prev-version}/` 历史版本目录 |
| **保留** | `99_回滚脚本.sql` **永远不动**（位置、内容、序号固定保留） |
| **拆分铁律** | DDL（`CREATE TABLE` / `ALTER TABLE` / `CREATE INDEX` / `DROP` / `ADD COLUMN` 等表结构变更）与 DML（`INSERT INTO` / `UPDATE` / `DELETE` / `MERGE` 字典或种子数据）**默认必须拆分到不同文件**，唯一例外见下方阈值规则 |
| **可合并阈值** | DDL + DML 合计**有效行**（不含注释、空行、`--` 行）**< 100 行** → 允许合并到 1 个文件；命名为 `01_<版本主题>.sql` |
| **强制拆分阈值** | DDL + DML 合计有效行 **≥ 100 行** → 必须拆 2+ 文件 |
| **再拆阈值** | 单个 DDL 或 DML 文件 **> 500 有效行** → 必须按业务模块或表再拆 |
| **命名规范** | 多文件 `<NN>_<业务名>(DDL\|初始化数据).sql`；NN 从 `01` 起按执行顺序连续编号；DDL/DML 同一序号空间混排（如 `01_用户表DDL.sql` / `02_用户字典初始化.sql` / `03_订单表DDL.sql` / `04_订单状态字典初始化.sql`）；`99_回滚脚本.sql` 序号保留 |
| **执行顺序原则** | 同业务的 DDL 必在 DML 之前（先建表后插数据）；跨业务按业务依赖顺序（被依赖方在前） |

**★ SQL 已在各环境执行完毕时的重组处置（消除"重命名打断三处对应关系"的判断真空）**：整理规则默认前提是"SQL 尚未在生产执行"，但发布时脚本可能已在研发/演示/生产各库执行完毕。两种情形口径：

- **SQL 尚未在生产执行** → 照常重组（重命名无副作用）。
- **SQL 已在各环境执行完毕** → **同样重组**（发布态归档不能因已执行就跳过），但**必须同步更新所有"按旧文件名绑定"的引用**，否则会打断三处对应关系：
  1. **`memory/{version}/{user}/.applied-sql.json`**（约定 6 幂等记录，按 `文件名 + sha256` 绑定）→ 把已执行文件的**文件名键**改为重组后新名（sha256 不变——内容守恒，见 3.3.7.3-c），使幂等记录继续命中、不误判"新文件未执行"而重跑；
  2. **`docs/deployment/{version}/部署流程/SQL执行台账.md`** → 文件名引用改新名，并在台账**新增「重组前后文件名对应关系」对照表**供运维/审计追溯；
  3. **所有引用旧 SQL 文件名的发布态文档**（`部署流程.md` / `配置项清单` / `checklist`，即 B 部分 3.3.7.7 已覆盖的对齐）。
- **★ 审计报告里的旧文件名不修改**（它们是当时的事实快照，非发布态引用），执行体**不得**因追求"全库替换"去改它们。
- **守恒仍是硬底线**：无论是否已执行，重组**只重排文件 + 重命名、绝不改任何 SQL 语句**（3.3.7.3-c 守恒校验按语句类型计数比对，不通过即中止保留原文件）。

#### Step 3.3.7.3：执行流程

**a) 扫描 + 解析（命令端用 Bash + AI 读）**：

```bash
SQL_DIR="docs/deployment/{version}/sql/增量"   # ⛔ 跨围栏取空会展开成 `ls /*.sql`（文件系统根 glob）
# 列出待整理文件（排除 99_回滚）
ls "$SQL_DIR"/*.sql 2>/dev/null | grep -v "99_回滚脚本.sql$"
```

然后由 PM Agent（命令的承载角色）逐一 Read 每个文件，统计：
- 每条语句类型（DDL / DML）
- 每条语句涉及的表名（用于按业务分组）
- 每条语句的有效行数（去除注释和空行）

**b) 编排新结构**：

按「3.3.7.2 整理规则」决策：
- 计算总有效行数：< 100 → 单文件 / ≥ 100 → 拆 DDL+DML / 任一 > 500 → 按业务再拆
- 同一业务表的 DDL 紧邻、DML 紧邻，按上线执行顺序排序
- 给每个目标文件分配 `NN_<业务名><DDL|初始化数据>.sql` 命名

**c) 写新文件到临时目录 + 内容守恒校验**：

```bash
SQL_DIR="docs/deployment/{version}/sql/增量"   # ⛔ 跨围栏取空 ⇒ 守恒基数恒 0，整理"恒通过"
TMP_DIR=$(mktemp -d)
# ⛔ 必须落盘：d) 是**另一次 Bash 调用**，`mktemp -d` 的结果既跨不过去、也无法重新派生。
#    d) 里 `TMP_DIR` 取空会展开成 `mv /*.sql "$SQL_DIR"/` —— 对文件系统根做 glob 的破坏性操作。
echo "$TMP_DIR" > .aidp-sqlreorg-tmpdir
# AI 把新文件内容写到 $TMP_DIR/<NN>_<中文名>.sql
# 守恒校验（防止漏掉某条 SQL）：
# ⛔ 必须先按**文件名**过滤再 cat（同 :98 的 `ls | grep -v "…\.sql$"` 口径）：
#    `cat *.sql | grep -v "99_回滚脚本.sql"` 过滤的是**内容行**，而 SQL 正文里不会出现自己的文件名
#    → 一行都滤不掉 → ORIG 把回滚脚本的 DROP/ALTER 也计进来，而 TMP_DIR 按 3.3.7.2「回滚脚本永远不动」
#    不含它 → 守恒**恒不相等**：只要项目有 99_回滚脚本.sql，SQL 归档整理**每次发布必失败**
#    （走「失败不阻塞」分支：删 TMP_DIR、原文件保留、每轮稳定新增同一条发布欠账，且 --finalize-docs 补跑也永远失败）。
ORIG_SQL_FILES=$(ls "$SQL_DIR"/*.sql 2>/dev/null | grep -v "99_回滚脚本\.sql$" || true)
ORIG_STMT_COUNT=$([ -n "$ORIG_SQL_FILES" ] && cat $ORIG_SQL_FILES | grep -cE "^(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE)\s" || echo 0)
NEW_STMT_COUNT=$(cat "$TMP_DIR"/*.sql 2>/dev/null | grep -cE "^(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE)\s" || echo 0)
if [ "$ORIG_STMT_COUNT" -ne "$NEW_STMT_COUNT" ]; then
  echo "FAIL: SQL 语句数不一致（原 $ORIG_STMT_COUNT vs 新 $NEW_STMT_COUNT），中止整理保留原文件"
  rm -rf "$TMP_DIR"; rm -f .aidp-sqlreorg-tmpdir
  # 走「失败不阻塞」分支
fi
```

**d) 守恒通过后 → 删原始 + 写新文件**：

```bash
# ⛔ 本围栏是**另一次 Bash 调用**：`SQL_DIR`（a 段）与 `TMP_DIR`（c 段）都不会跨过来。
#    取空后这三行分别退化为 `ls /*.sql`、`xargs git rm -f`（无参报错）、`mv /*.sql /` ——
#    全仓唯一一处"变量取空后仍执行破坏性文件操作"的围栏，故两个都 fail-closed，绝不允许空值往下走。
SQL_DIR="docs/deployment/{version}/sql/增量"
TMP_DIR=$(cat .aidp-sqlreorg-tmpdir 2>/dev/null || true)
[ -d "$SQL_DIR" ] || { echo "⛔ $SQL_DIR 不存在 → 放弃 d) 段，原文件保留"; exit 1; }
[ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ] || { echo "⛔ 取不到 c) 段的 TMP_DIR → 放弃 d) 段，原文件保留"; exit 1; }

# 列出待删除原文件（保留 99_回滚脚本.sql）
TO_DELETE=$(ls "$SQL_DIR"/*.sql | grep -v "99_回滚脚本.sql$")

# git rm 旧（保留 git 历史可溯源）
echo "$TO_DELETE" | xargs git rm -f

# 移入新文件
mv "$TMP_DIR"/*.sql "$SQL_DIR"/
rmdir "$TMP_DIR"; rm -f .aidp-sqlreorg-tmpdir

# git add 新文件（Step 3.4.1 的 git add docs/deployment/{version}/ 整个部署目录也会捎上，这里 add 一下保险）
git add "$SQL_DIR"/*.sql
```

**e) 同步数据库基线（必跑）**：

整理后表结构语义不变，但**文件路径变了**。若 `memory/databaseBaseline.md` 含具体文件名引用（如"参见 `docs/deployment/{version}/sql/增量/01_用户表.sql`"），需用 Edit/sed 替换为新路径名。

```bash
# 简单 grep 检测是否需要联动更新
grep -nE "docs/deployment/{version}/sql/增量/[^'\"]*\.sql" memory/databaseBaseline.md && echo "需手工更新 baseline 引用"
```

如有引用，PM Agent 用 Edit 工具按新文件名替换。

#### Step 3.3.7.4：输出摘要

```
🗄 SQL 文件整理完成（{version}）：
   原始：{N1} 个文件 / {L1} 行 SQL（不含 99_回滚）
   整理后：{N2} 个文件
     • 01_<业务名>DDL.sql ({K1} 行)
     • 02_<业务名>初始化数据.sql ({K2} 行)
     • ...
     • 99_回滚脚本.sql（保留不动）
   守恒校验：✓ 语句数一致（{ORIG_STMT_COUNT} 条）
```

#### Step 3.3.7.5：失败处置（不阻塞发布）

- 守恒校验失败（新旧语句数不一致） → 删 `$TMP_DIR`，保留原文件不动，发布报告 Step 3.6 加 WARN「⚠️ SQL 整理已跳过（守恒校验失败），原文件保留；建议手工整理后下次发布合并入库」，**并登记 `docs/audit/{version}/发布欠账.md`**（步骤=Step 3.3.7 A，定位=`sql/增量/` 目录 + 守恒差异语句数，补跑命令 `/version {version} --finalize-docs`；台账格式见「发布期整理欠账台账」段）
- 文件读取失败 / 解析异常 → 同上，不阻塞发布
- **唯一阻塞情形**：`$SQL_DIR` 整个目录被意外破坏（如 git 误删但未 commit） → 中断 `/version` 让用户先恢复

#### Step 3.3.7.6：与下游协作

- Step 3.4.1 的 `git add docs/deployment/{version}/`（整个部署目录）会把 A 部分 SQL 的 `git rm` 旧 + `git add` 新、以及 B 部分完善后的 `部署流程/`·`配置文件/`·`checklist` 一并落到 `release({version})` 提交
- Step 3.6 发布报告新增「部署产物整理」段，引用 3.3.7.4（SQL）+ 3.3.7.7（其余产物）的摘要

> **A 部分设计 vs 整理的边界（避免误解）**：A 部分（SQL 整理）**不修改任何 SQL 内容**（语句、字段、注释、表名一概守恒），**只重新组织文件结构 + 重命名**。SQL 内容的设计审查在 `/sprint-design` Step 3 由 `dev-logic-architect` SKILL Module D 完成；本步骤是发布前的归档动作，与设计层职责正交。

