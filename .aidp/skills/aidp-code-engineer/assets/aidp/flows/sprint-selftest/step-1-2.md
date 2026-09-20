# sprint-selftest · Step 1 详情〔2/2〕— 调用返回后落盘核验归一 + 补充模式

> 本文件是 `/sprint-selftest` 命令 **Step 1** 的完整详细步骤 **第 2 片（共 2 片）**，接续 `step-1-1.md`，覆盖：调用 dev-manual-testcase 返回后的**落盘核验 + 研发自测方案归一** bash（用例/方案缺失 = 硬阻断 `exit 1`）+ **补充模式**（`--supplement={NN}` 前置归位/子目录化脚本 + 落盘/回写规则）。调用前的准备与参数见 `step-1-1.md`。
>
> ⚠️ **权威性**：进入 Step 1 后，以 `step-1-1.md` + 本片为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-selftest/step-1-2.md`。理据/根因见同目录 `rationale.md`。

---

**调用返回后必须执行 bash 落盘核验 + 研发自测方案归一**（三件套防御 + 新 SKILL 适配）：

```bash
# Step 1 调用结束后的"落盘核验 + 归一"（索引态：00_索引.md + 01_研发自测方案.md + 用例从 02_ 起）
V_TEST=docs/testing/{version}
DST_DIR="$V_TEST/研发自测"
PLAN_DST="$DST_DIR/01_研发自测方案.md"   # 索引态方案在 01_（旧锚 00_研发自测方案.md grandfather 兼容）

# ① 用例落盘核验（索引态用例从 02_ 起；grandfather 旧布局用例在 01_/无前缀；归一前先广搜确认 SKILL 确有用例产出）
TESTCASE_ANY=$(find "$V_TEST" -type f \( -name "02_*自测用例*.md" -o -name "02_自测用例-总览.md" -o -name "01_*自测用例*.md" -o -name "01_自测用例-总览.md" -o -name "全量自测用例*.md" -o -name "增量自测用例*.md" -o -name "研发自测.md" \) 2>/dev/null | head -1)
if [ -z "$TESTCASE_ANY" ]; then
  echo "❌ Step 1 失败：dev-manual-testcase SKILL 未产出任何用例文档（索引态应有 02_全量自测用例.md / 02_增量自测用例.md / 02_自测用例-总览.md 之一）"
  echo "   - 可能原因：① SKILL 未被实际调用（漏触发）② SKILL 输出到错误目录 ③ SKILL 内部 QR 失败但未通知命令端"
  echo "   - 处置：暂停命令；用户核对 SKILL 输入参数后重跑 /sprint-selftest {version}（研发自测唯一入口，勿直调 SKILL——直调会跳过本落盘核验与目录归一）"
  exit 1
fi

# ② ★ 研发自测索引 + 方案 + 用例整体归一（适配 SKILL「文件命名总则」NN_ 前缀铁律）
#    索引态 SKILL 产物：00_索引.md（专职索引）+ 01_研发自测方案.md + 02_全量/增量自测用例.md|02_自测用例-总览.md + 03_~ 业务用例 + 98_ / 99_
#    输出在 {测试文档目录}/{项目名}/ 子目录、文件名已带 NN_ 前缀；命令端事后 git mv 整体归一到 $DST_DIR/，
#    去 {项目名} 子目录、保留 NN_ 前缀不改名（★ 严禁把单文件用例改回无前缀的 全量自测用例.md——违反 SKILL「同目录所有文件一律带 NN_ 前缀」铁律）
#    （旧锚 grandfather：00_研发自测方案.md + 01_ 用例…；整目录搬迁保留原名，末尾兜底把 stale 00_ 方案归一到 01_）
PLAN_SRC=$(find "$V_TEST" \( -name "01_研发自测方案*.md" -o -name "00_研发自测方案*.md" \) -type f 2>/dev/null | head -1)
if [ -n "$PLAN_SRC" ]; then
  SRC_DIR=$(dirname "$PLAN_SRC")
  if [ "$SRC_DIR" != "$DST_DIR" ]; then
    mkdir -p "$DST_DIR"
    for f in "$SRC_DIR"/*.md; do          # 整目录搬迁全部产物（含 00_索引.md / 01_研发自测方案.md / 02_~ 用例），NN_ 前缀原样保留
      [ -f "$f" ] && git mv "$f" "$DST_DIR/$(basename "$f")"
    done
    [ "$SRC_DIR" != "$V_TEST" ] && [ -z "$(ls -A "$SRC_DIR" 2>/dev/null)" ] && rmdir "$SRC_DIR"
    echo "✅ 研发自测索引 + 方案 + 用例已整体归一到 $DST_DIR/（去 {项目名} 子目录、保留 NN_ 前缀）"
  fi
  # 归一到 SKILL 命名总则规范名：① 旧 SKILL 无前缀/带 {项目名}-v{版本} 后缀散文件 → 规范 NN_ 名（用例在 02_）；② 总览/单文件用例保留 SKILL 原名；③ stale 旧锚 00_方案（无 01_方案时）归一到 01_
  for f in "$DST_DIR"/*.md; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in
      全量自测用例-*)                       git mv "$f" "$DST_DIR/02_全量自测用例.md" ;;
      增量自测用例-*)                       git mv "$f" "$DST_DIR/02_增量自测用例.md" ;;
      02_自测用例-总览.md)                   : ;;   # 已是索引态规范名，保留
      02_*总览*.md)                         git mv "$f" "$DST_DIR/02_自测用例-总览.md" ;;   # 总览变体名 → 规范 02_ 名
      00_研发自测方案.md)                    [ -f "$DST_DIR/01_研发自测方案.md" ] || git mv "$f" "$DST_DIR/01_研发自测方案.md" ;;  # stale 旧锚归一到 01_
    esac
  done
  # 回写用例文档头部「自测方案来源」链接，统一指向归一后路径 01_研发自测方案.md（兼容 SKILL 历史命名后缀与旧锚 00_）
  grep -rlE '0[01]_研发自测方案(-[^.]+-v[^.]+)?\.md' "$DST_DIR" 2>/dev/null | while read f; do
    sed -i -E 's|0[01]_研发自测方案(-[^.]*-v[^.]*)?\.md|01_研发自测方案.md|g' "$f"
  done
fi
# ★ 方案缺失 = 硬阻断（与上方用例核验对齐）：缺方案直接拦截，不单依赖易被跳过的 Step 2 item 8
if [ ! -f "$PLAN_DST" ]; then
  echo "❌ Step 1 失败：未产出研发自测方案文档 \$PLAN_DST（dev-manual-testcase SKILL 第零步 0.2 强制生成、「自测方案对齐与引用闭环」维度不可豁免）"
  echo "   - 可能原因：① SKILL 第零步 0.2 被跳过（直奔用例生成）② SKILL 输出名/目录与命令端归一逻辑不匹配 ③ SKILL 内置多维度后检（含自测方案对齐维度，详见 SKILL.md）整段被跳过"
  echo "   - 处置：暂停命令；用户核对 SKILL 第零步是否真实落盘 01_研发自测方案.md 后重跑 /sprint-selftest {version}（研发自测唯一入口，勿直调 SKILL）"
  exit 1
fi

echo "✅ Step 1 落盘核验通过（专职索引 + 用例 + 研发自测方案均已落盘）"
```

**补充模式**（`--supplement={NN}`）：

```
额外 prompt 输入：
- 输入变更摘要（含 PRD + 原型变更）+ 各类补充文档（研发需求 / 设计 / 计划）
- 原研发自测用例.md（基线，只读）

skill 工作要求：只针对本次变更涉及的功能点输出新增 / 修订用例，未变功能不重复；原型变更会改变用例的"操作对象"和"预期现象"，必须重点对齐

★ 补充模式前置：SKILL 输出归一 + 主文档子目录化检查（按 CLAUDE.md 约定 15 铁律）

调 SKILL 之前命令端必须执行：

  V=docs/testing/{version}
  # ★ 第一步：历史扁平单文件兜底归位（历史项目的扁平 研发自测用例.md / 研发自测.md → 统一目录名 研发自测；
  #          当前流程 Step 1 已直接产出 研发自测/ 子目录 + NN_ 前缀产物，本步仅对旧布局升级生效，SKILL 内部无感知）
  [ -f "$V/研发自测用例.md" ] && [ ! -e "$V/研发自测.md" ] && git mv "$V/研发自测用例.md" "$V/研发自测.md"
  [ -d "$V/研发自测用例"   ] && [ ! -e "$V/研发自测"   ] && git mv "$V/研发自测用例"   "$V/研发自测"
  # ★ 第二步：扁平单文件→子目录化（docs/testing/{version}/ 是"共享目录"，
  #          扁平单文件补充会污染父目录 → 强制子目录化；仅旧布局兜底，新流程目录已存在不触发）
  MAIN_SINGLE=$V/研发自测.md
  MAIN_DIR=$V/研发自测
  if [ -f "$MAIN_SINGLE" ] && [ ! -d "$MAIN_DIR" ]; then
    mkdir -p "$MAIN_DIR"
    # ★ 用例主文档迁为 02_全量自测用例.md（索引态：00_ 索引 / 01_ 研发自测方案 / 用例从 02_ 起，约定 14/15 + 本命令 Step 1）
    git mv "$MAIN_SINGLE" "$MAIN_DIR/02_全量自测用例.md"
    echo "✅ 已将单文件主文档 $MAIN_SINGLE 迁入子目录 $MAIN_DIR/02_全量自测用例.md（00_ 索引 / 01_ 方案 / 用例 02_，补充模式触发）"
  fi
  # ★ 第三步：历史根目录散落的补充文件（如 V0.X 的 docs/testing/V0.X/研发自测用例-补充-NN.md
  #          或 V0.X 的 研发自测-补充-NN.md）一并归位到子目录
  for f in $V/研发自测用例-补充-*.md $V/研发自测-补充-*.md; do
    [ -f "$f" ] && git mv "$f" "$MAIN_DIR/$(basename "$f")"
  done

落盘：docs/testing/{version}/研发自测/<NN>_<业务主题>.md（文件名不带"补充"字眼，按 CLAUDE.md 约定 15 统一数字前缀规则 — NN = 内容主文档目录现存最大序号 + 1，用例从 02_ 起续编）
★ 一律在 研发自测/ 同目录平铺续编，严禁拆二级子目录：SKILL「文件命名总则」要求同目录 NN_ 前缀平铺，
  其硬门 check_testcase_format.py 只 glob("*.md") 非递归扫描，落进子目录的用例会整体逃检。
  用例数多时按 SKILL「多文件拆分」在同目录继续 03_/04_… 自增（拆分阈值与目标文件数以 SKILL 为准）。

回写：在研发自测**专职索引** `00_索引.md` 登记该增量行（类型=补充 + 生成时间；主文档行 = 方案 `01_研发自测方案.md` + 用例总览 `02_自测用例-总览.md`（多文件）/ `02_全量自测用例.md`（单文件）/ 历史 `00_研发自测.md`·`01_全量自测用例.md`（旧布局兜底）——★ 研发自测目录已对齐通用范式，导航锚 = `00_索引.md`（SKILL 第八步收尾产出，见本命令 Step 1）；`01_研发自测方案.md` §8「用例索引」段是方案↔用例的套件级业务导航，由 SKILL 维护，与 `00_索引.md` 文档族清单职责不同、并存不冲突。旧锚 `00_研发自测方案.md` grandfather 兼容识别）
新增用例 ID 全局唯一（继承原主文档的编号空间，往后递增）
```

