# sprint-design · 输出前硬门 详情（回检清单 + 三合一回写校验）

> 本文件是 `/sprint-design` 命令 **输出前硬门**的完整详细步骤，由命令主体（`{{AIDP_HOME}}/commands/sprint-design.md`）在**进入该段（跑完 Step 2~6 后）时用 Read 工具按需加载**——把 A 回检清单 bash 块 + B 三合一回写校验脚本（基线 + ADR + 金额字段）从"每次调用整体入上下文"改为"走到该段才载"。命令主体只保留该段的**硬门提醒 + 骨架表 + Read 指针**。
>
> ⚠️ **权威性**：进入本段后，**以本文件为准逐项执行**——用 Bash 工具真实执行两个 bash 块、逐行填「🔍 输出前回检」表，B 块退出码必须为 0 且看到通过字样才算完成；不得凭命令主体骨架或记忆略过。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/step-输出前硬门.md`。理据/根因见同目录 `rationale.md`。

---

## ★ 输出前硬门：回检清单 + 三合一回写校验（不可跳过）

> 🛑 **STOP — 跑完 Step 2~6 后必须在此暂停：先跑下面「A 回检清单」bash 块填完表，再跑「B 三合一回写校验」脚本（基线 + ADR + 金额字段），两者都过才决定能否输出"✅ 完成"。**
>
> 跳过本硬门 = 严重违规。**Claude 长任务跑到这里时如果直接输出"✅ /sprint-design 完成"而没出现下方"🔍 输出前回检"块 + `✅ 基线 + ADR + 金额字段 三合一回写校验通过` 字样** → 用户有权要求"重跑硬门 / 回滚此次输出"。

**关键约束**：Claude 在输出"✅ /sprint-design 完成"**之前**，**必须**：
1. 真实执行下方两个 bash 块（A 回检清单 + B 三合一回写校验）— 用 Bash 工具跑，不是默念也不是估算
2. 把 A 块每项 Pass/Fail 结果写入"🔍 输出前回检"块（**逐行填表**，不能省略）
3. B 块退出码必须为 `0` 且看到 `✅ 基线 + ADR + 金额字段 三合一回写校验通过` 这行输出；退出码非 0 → 按报错补 `memory/databaseBaseline.md` / `memory/systemPatterns.md` / 修复 DECIMAL 金额字段后**重跑**到 0
4. **任一 Fail（A 块任一项 / B 块退出码非 0）→ 立即输出"❌ 回检未通过：缺失项 …"，停下来请用户决定**（要求 skill 重新生成 / 人工补齐 / 强制放行）；不得用"基本通过""主要项通过"等模糊措辞绕过

### A. 回检清单 bash 块

```bash
# ⛔ `cd` 之后**不得再用仓库根相对路径调脚本**——`{{AIDP_HOME}}/skills/...` 在版本目录下不存在，
#    整条命令 `No such file` → `$?` 非 0 → 被当成"检查未通过"或（配 `>/dev/null 2>&1` 时）
#    静默记成入参错不计 Fail。故先把仓库根固化成绝对路径再 cd。
REPO_ROOT=$(git rev-parse --show-toplevel)
# 进入版本目录
cd docs/design/detail/{version}/

# 1) 文件数 + NN_ 前缀回检（Step 1.5 落盘约束 + Step 1.8 检查项 1）
FILES=$(ls *.md 2>/dev/null | wc -l)
BARE_NAMES=$(ls *.md 2>/dev/null | grep -vcE '^[0-9]{2}_')
HAS_INDEX=$(ls 00_索引.md 2>/dev/null | wc -l)

# 2) L1 文档级头部上游引用块（Step 1.8 L1 检查；关键词与 dev-logic-architect SKILL 一致）
L1_MISS=0
for f in *.md; do
  head -20 "$f" | grep -qE '研发 PRD 来源[:：]|产品需求文档来源[:：]|原型来源[:：]|高保真设计来源[:：]' || L1_MISS=$((L1_MISS+1))
done

# 3) 对外接口规范（Step 1.7 — 仅 HAS_OPEN_API=true 时）
# 4) 需第三方提供接口职责边界（Step 1.7.5 — 仅 HAS_THIRD_PARTY_DEP=true 时）
# 5) 字典/枚举强制生成枚举类（step-1.6「SKILL 脚本复核」结果 — 仅含 A.4 章节的文件触发；「字典/枚举强制生成枚举类」维度 Critical）
HAS_A4=$(grep -lE 'A\.4|字典与枚举|字典枚举' *.md 2>/dev/null | wc -l)
# 5b) ER 图 + 禁 FK + 索引列 NOT NULL（step-1.6「SKILL 脚本复核」的 check_er_and_fk.py + check_index_not_null.py — A.3 章节存在即跑；「ER 关系图与外键约束」+「索引列 NOT NULL 强制」维度 Critical）
HAS_A3=$(grep -lE '^## A\.3|数据表设计|数据库设计' *.md 2>/dev/null | wc -l)
# 6) 待澄清问题清单（不中断原则 — 单文件含「Module E: 待澄清问题清单」或多文件含 99_待澄清问题清单.md）
PENDING_CH=$(grep -l 'Module E\|待澄清问题清单' *.md 2>/dev/null | wc -l)
PENDING_FILE=$(ls 99_待澄清问题清单.md 2>/dev/null | wc -l)
# 7) 上游溯源覆盖率 —— ⛔ 判定**全权交 SKILL 脚本**，命令端不自算、不自定阈值（约定 21）。
#    退出码：0=达标 / 1=未达标 / 2=入参错（修参数重跑，不记 Fail）。阈值由脚本内置（逐类分别判），
#    ⛔ 命令端不得另设"三类合计"之类口径（分母不同，会把 SKILL 判 Fail 的产物判 Pass）。
# ⛔ 加了 `--json` 却把 stdout 全丢、只取退出码 = 撞进本命令另一分片（step-1.6）刚点名要防的假绿：
#   该脚本三类元素**一个都没识别到**时 return 0，`--json` 里 `skipped:true`。标题形态一漂移，
#   整道 Critical 溯源门就静默全绿。判定必须「退出码 0 **且** skipped != true」。
UPS_JSON=$(python3 "$REPO_ROOT/{{AIDP_HOME}}/skills/dev-logic-architect/scripts/check_upstream_reference.py" . --json 2>/dev/null); UPS_EXIT=$?
UPS_SKIPPED=$(printf '%s' "$UPS_JSON" | python3 -c "import json,sys;print(1 if json.load(sys.stdin).get('skipped') else 0)" 2>/dev/null || echo -1)

cd -
```

**回检判定**：

| # | 检查项 | Pass 条件 | 当前结果 |
|---|--------|---------|---------|
| 1a | 文件数与编号 | `FILES ≤ 1`（单文件，免检）OR `FILES ≥ 2 && BARE_NAMES == 0 && HAS_INDEX == 1` | { Pass / Fail：FILES=N, BARE=N, INDEX=N } |
| 1b | 拆分文件数控制 | `FILES ≤ 5` 或 单文件最大行数 ≥ 800 | { Pass / Fail } |
| 2 | L1 文档级头部 | `L1_MISS == 0`（每个文件头部前 20 行都含上游引用块） | { Pass / Fail：缺失 M 个文件 } |
| 3 | 对外接口规范（HAS_OPEN_API=true） | Step 1.7 9 项硬规范全部 ✓ | { Pass / N/A / Fail } |
| 4 | 第三方接口职责边界（HAS_THIRD_PARTY_DEP=true） | Step 1.7.5 5 项 ✓ | { Pass / N/A / Fail } |
| 5 | 字典/枚举代码契约（HAS_A4 > 0） | step-1.6「SKILL 脚本复核」的 `check_enum_contract.py` 退出码 = 0（`2`=入参错 → 修参数重跑，**不记 Fail**）；「字典/枚举强制生成枚举类」维度 Critical | { Pass / N/A / Fail } |
| 5b | ER 图 + 禁 FK + 索引列 NOT NULL（HAS_A3 > 0） | step-1.6「SKILL 脚本复核」的 `check_er_and_fk.py` + `check_index_not_null.py` 退出码均 = 0（`2`=入参错 → 修参数重跑，**不记 Fail**）；「ER 关系图与外键约束」+「索引列 NOT NULL 强制」维度 Critical | { Pass / N/A / Fail } |
| 5c | 文本字段长度冗余 3×（HAS_A3 > 0） | ⚠️ **告警档、不计 Fail**：`check_text_field_length.py` 在 SKILL 侧未接入 QR 步骤 0（口径以 `dev-logic-architect/references/quality-review-checklist.md` 为准）；有发现记入回检小结交人判 | { Pass / N/A / ⚠️ 告警 } |
| 5d | 列表页数据量级与分页策略（约定39-R13；含列表页即适用） | step-1.6「SKILL 脚本复核」的 `check_list_page_scale.py` **传目录**、退出码 = 0（`2`=入参错 → 修参数重跑，**不记 Fail**）**且** `--json` 的 `findings[]` 无 `level == "Important"`——⛔ S1「一张子表都没有」判 Important、**不占退出码**，只看 `$?` 会把它读成通过；「性能与边界限制」检查项 5 子项 Critical | { Pass / N/A / Fail } |
| 6 | 待澄清问题清单（不中断原则；配合 SKILL「待澄清问题清单完整性」维度） | 单文件 `PENDING_CH ≥ 1`（即含 Module E 章节）OR 多文件 `PENDING_FILE == 1`（即存在 `99_待澄清问题清单.md`，即便无待澄清项也要保留标题）；并且 D-NNN/Q-NNN 编号合法 + 🔧 暂行方案列无空白 + 不接受模糊表述（grep `待确认\|按常规处理\|参考行业惯例` 命中 = 0） | { Pass / Fail } |
| 7 | L2/L3 溯源覆盖率（SKILL「上游溯源完备性」维度） | `UPS_EXIT == 0` **且 `UPS_SKIPPED == 0`**（⛔ `skipped=true` = 未实质核验、不得当通过，口径同 step-1.6；阈值与逐类口径由 `check_upstream_reference.py` 内置，**命令端不复述**；`2`=入参错 → 修参数重跑，**不记 Fail**）| { Pass / Fail } |
| 8 | **货币金额字段整数化（「货币金额字段整数化」维度 Critical）** | 由下方「B 三合一回写校验」脚本第 3 段统一核验：金额字段全部 `BIGINT`（或 64 位整数等价）+ `COMMENT` 含"单位:..."声明 + 无 `FLOAT/DOUBLE/REAL`（调上游 `check_money_field.py`）；本项目无金额字段时标 N/A | { Pass / N/A / Fail } |

**输出格式**（每项必填）：

```
🔍 输出前回检（逐项对应上方判定表 12 项，不可省略）：
  1a. 文件数 + NN_ 前缀：{✅ Pass / ❌ Fail（FILES=N, BARE=N, INDEX=N）}
  1b. 拆分数量控制：{✅ / ⚠️ / ❌}
  2. L1 文档级头部上游引用：{✅ Pass / ❌ Fail（缺 M 个文件）}
  3. 对外接口规范（HAS_OPEN_API）：{✅ / N/A / ❌}
  4. 第三方接口职责边界（HAS_THIRD_PARTY_DEP）：{✅ / N/A / ❌}
  5. 字典/枚举代码契约（HAS_A4）：{✅ / N/A / ❌}
  5b. ER 图 + 禁 FK + 索引列 NOT NULL（HAS_A3）：{✅ / N/A / ❌}
  5c. 文本字段长度冗余 3×（HAS_A3，告警档）：{✅ / N/A / ⚠️}
  5d. 列表页数据量级与分页策略（约定39-R13）：{✅ / N/A / ❌（含 Important S1 也记 ❌）}
  6. 待澄清问题清单：{✅ / ❌}
  7. L2/L3 溯源覆盖率：{覆盖率 N%；✅ / ⚠️ / ❌}
  8. 三合一回写校验（基线 + ADR + 金额字段）：{✅ 退出码 0 + 看到"✅ 基线 + ADR + 金额字段 三合一回写校验通过" / ❌ 退出码非 0，已按报错补写重跑}

  总评：{✅ 全部通过 → 进入 ## 输出 / ❌ 不通过 → 列出 Fail 项，询问用户决定}
```

### B. 三合一回写校验脚本（基线 + ADR + 金额字段）

> ⚠️ **本脚本是 `/sprint-design` 完成的硬门槛，不是描述性脚本**。Claude 在宣布"sprint-design 完成"**之前**，**必须**通过 Bash 工具**真实执行**下述脚本并**解析退出码**：
> - `exit 0` → 通过，可标完成
> - `exit 1` → **不允许**标完成；必须按报错提示补写 `memory/databaseBaseline.md` / `memory/systemPatterns.md` / 修复 DECIMAL 金额字段后**重跑**直到通过
>
> 不执行本脚本等于 sprint-design 未完成。命令执行器**严禁**在未跑此脚本的情况下回执"已完成"。

```bash
set -e

VERSION="<本次版本号>"           # 由命令端展开为实际版本号，如 V0.6
DESIGN_DIR="docs/design/detail/$VERSION"
# SQL 扫描扩展到多个来源（防止增量 DDL 落在非标准目录被漏检）
SQL_PATHS=(
  "docs/deployment/$VERSION/sql/增量"          # ★ 最终 SQL 落位（Step 3.2 搬迁后）
  "code/sql/v$VERSION"                    # SKILL 暂存位（带 v 前缀，实际输出）
  "code/sql/$VERSION"                     # 兼容：无 v 暂存位残留 / legacy 存量（grandfather）
  "docs/design/detail/$VERSION"          # 设计文档内嵌的 ```sql 块也算
)

# ============================================================
# 1) 数据库基线回写：本版本数据库设计.md / SQL 中新增的表必须出现在 databaseBaseline.md
# ============================================================
# 设计文档：识别"## T_ORDER" / "### t_user" 等表名章节标题（覆盖 V0.6 真实形态）
NEW_TABLES_DESIGN=$(grep -hEo '#{2,4}\s+[`"]?[A-Z_][A-Z0-9_]{2,}[`"]?|`[a-zA-Z_][a-zA-Z0-9_]{2,}`' \
  "$DESIGN_DIR"/数据库设计.md "$DESIGN_DIR"/0?_数据库设计*.md 2>/dev/null \
  | grep -oE '[A-Z_][A-Z0-9_]{2,}|[a-z_]{3,}' \
  | grep -E '^(t_|T_|sys_|biz_|SYS_|BIZ_)' | sort -u)
NEW_TABLES_SQL=""
for path_glob in "${SQL_PATHS[@]}"; do
  for sql_file in $path_glob/*.sql; do
    [ -f "$sql_file" ] || continue
    found=$(grep -hiEo 'CREATE TABLE[[:space:]]+(IF[[:space:]]+NOT[[:space:]]+EXISTS[[:space:]]+)?[`"]?[a-zA-Z_]+' "$sql_file" \
      | awk '{print $NF}' | tr -d '`"' || true)
    NEW_TABLES_SQL="$NEW_TABLES_SQL"$'\n'"$found"
  done
done
NEW_TABLES_SQL=$(echo "$NEW_TABLES_SQL" | sort -u | grep -v '^$' || true)
ALL_NEW=$(echo -e "$NEW_TABLES_DESIGN\n$NEW_TABLES_SQL" | sort -u | grep -v '^$' || true)

MISSING_IN_BASELINE=""
for t in $ALL_NEW; do
  # 大小写不敏感 + 词边界匹配
  if ! grep -qiE "(^|[^a-zA-Z_])$t($|[^a-zA-Z_])" memory/databaseBaseline.md 2>/dev/null; then
    MISSING_IN_BASELINE="$MISSING_IN_BASELINE\n  - $t"
  fi
done
if [ -n "$MISSING_IN_BASELINE" ]; then
  echo "❌ 数据库基线漂移：以下新增表未追加到 memory/databaseBaseline.md：$MISSING_IN_BASELINE"
  echo "   补写步骤：① 打开 memory/databaseBaseline.md；② 按版本章节追加每张表（表名 + 用途 + 字段清单）；③ 重跑本脚本"
  exit 1
fi

# ============================================================
# 2) ADR 回写：详设/架构文档提到"架构决策 / 选型变更 / ADR-"时，systemPatterns 必须有改动
# ============================================================
ADR_KEYWORDS=$(grep -lE "架构决策|选型变更|ADR-|Architecture Decision" "$DESIGN_DIR"/*.md docs/architecture/*.md 2>/dev/null | wc -l)
if [ "$ADR_KEYWORDS" -gt 0 ]; then
  if git diff --quiet HEAD -- memory/systemPatterns.md 2>/dev/null; then
    echo "❌ ADR 漂移：详设/架构文档提到架构决策，但 memory/systemPatterns.md 未更新"
    echo "   补写步骤：① 在 systemPatterns.md 追加 ADR-NNN（决策点/上下文/替代方案/影响/回归路径）；② 重跑本脚本"
    exit 1
  fi
fi

# ============================================================
# 3) ★ 金额字段「货币金额字段整数化」维度强制校验（调用上游 check_money_field.py）
# ============================================================
# 上游 dev-logic-architect/scripts/check_money_field.py 已支持双路径扫描：
#   - ```sql DDL 块（CREATE TABLE 风格）
#   - Markdown 字段表格（| 字段名 | 类型 | ... | 备注 | 风格，AIDP 主流形态）
# 单层调用即可，无需命令侧 grep 兜底
MONEY_CHECK_SCRIPT="{{AIDP_HOME}}/skills/dev-logic-architect/scripts/check_money_field.py"
if [ ! -f "$MONEY_CHECK_SCRIPT" ]; then
  MONEY_CHECK_SCRIPT="{{AIDP_HOME}}/../skills/aidp-code-engineer/assets/aidp/skills/dev-logic-architect/scripts/check_money_field.py"
fi
if [ -f "$MONEY_CHECK_SCRIPT" ]; then
  CRITICAL_COUNT=$(python3 "$MONEY_CHECK_SCRIPT" "$DESIGN_DIR" --json 2>/dev/null \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print(sum(1 for i in d.get('issues',[]) if i.get('severity')=='Critical'))" 2>/dev/null || echo "0")
  if [ "${CRITICAL_COUNT:-0}" -gt 0 ]; then
    echo "❌ 金额字段「货币金额字段整数化」维度不通过：发现 $CRITICAL_COUNT 个 Critical 问题（DECIMAL/FLOAT 金额字段）"
    python3 "$MONEY_CHECK_SCRIPT" "$DESIGN_DIR" 2>&1 | sed 's/^/   /'
    echo "   修复步骤：金额字段类型改为 BIGINT + COMMENT 加'单位:分'/'单位:厘'等声明（见 docs 货币单位对照表 references/currency-unit-reference.md）；重跑本脚本"
    exit 1
  fi
else
  echo "⚠️ 未找到 check_money_field.py（应位于 {{AIDP_HOME}}/skills/dev-logic-architect/scripts/），跳过「货币金额字段整数化」维度校验"
fi

echo "✅ 基线 + ADR + 金额字段 三合一回写校验通过"
```

**Claude 执行 checklist**（每条都必须真实做到）：
1. ☐ 我已经用 Bash 工具**真实执行**了上述脚本（而不是只贴出来给用户看）
2. ☐ 退出码是 `0`（如非 0，我已按报错提示补写并重跑直到 0）
3. ☐ 我看到了"✅ 基线 + ADR + 金额字段 三合一回写校验通过"这行输出
4. ☐ 只有上述三条都满足，我才能向用户回执"sprint-design 完成"

> 🚨 **架构红线**：跳过本脚本等同于交付了未经验证的设计文档。

