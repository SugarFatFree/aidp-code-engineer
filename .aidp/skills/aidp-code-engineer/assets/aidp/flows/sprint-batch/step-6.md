# sprint-batch · Step 6 详情（浏览器仿真测试链路 6.0–6.6）

> 本文件是 `/sprint-batch` 命令 **Step 6**（编排 `/sprint-aiauto-test` 的浏览器仿真测试链路）的完整详细步骤，由命令主体在**进入 Step 6 时用 Read 工具按需加载**。命令主体只保留硬门 + 6.0–6.6 骨架表 + 指向本文件的指针。
>
> ⚠️ **权威性**：进入 Step 6 后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤（6.0 跳过判定 / 6.0.5 SQL 已应用校验 / 6.0.6 部署流程文档校验 / 6.1 用例存在性 / 6.2 deployment 配置 / 6.3 部署完成确认 / 6.4 baseline 预写 + 调 aiauto-test / 6.5 问题回写 / 6.6 兜底）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-batch/step-6.md`。理据/根因见同目录 `rationale.md`。

---

### Step 6：浏览器仿真测试链路（★ 编排 `/sprint-aiauto-test`）

> ⛔ **本步骤是 sprint-batch 与 sprint-aiauto-test 的衔接桥**。Step 1~5 跑的是"代码开发 + 单元/集成验证"，Step 6 跑的是"部署到运行环境后的真人视角浏览器仿真测试"，端到端闭环。（余下理据见同目录 `rationale.md`）

#### Step 6.0 跳过条件判定（按优先级）

> ⛔ **6.0.5 / 6.0.6 是【部署前】安全网，不受本跳过判定管辖——先跑它们，再做下表判定**。
> 它们校的是「SQL 有没有真的应用到库」与「部署流程文档在不在」，与"跑不跑浏览器测试"无关；
> 放在判定之后会被 `--skip-aiauto-test` 连坐，而 7×24 主路径恒带该 flag（根因见
> `.aidp/flows/sprint-autopilot/rationale.md`「部署前安全网为何要在 autopilot 侧再跑一次」）。

| 条件 | 行为 |
|------|------|
| 命令带 `--skip-aiauto-test` | 跳到「最终汇总报告」（6.0.5/6.0.6 已在本判定之前执行完），报告里标 `⏭️ 已跳过浏览器测试（用户显式 --skip-aiauto-test）` |
| Step 3 循环出现**硬失败**导致中断（编译/构建失败 / 设计文档缺失）| 直接跳过，报告里标 `⏭️ 已跳过（Step 3 硬失败，无可测产物）` |
| PRD 头部 `autopilot_decisions.deployment.mode == none` | 直接跳过，报告里标 `⏭️ 已跳过（该版本 deployment.mode=none）` |
| 上述全不命中 | 进 6.1 |

#### Step 6.0.5 ★ SQL 已应用校验（部署前安全网 — 防「部署后表缺失报错」，约定 6）

> 本版本详细设计若含数据库，SQL 落 `docs/deployment/{version}/sql/增量/`，由 `/sprint-dev` 后端 Phase 1.2 Step 1 **开发期自动应用到开发库**（检测驱动、幂等，约定 6）。本步是**部署/测试前的兜底核验**——堵住边界（本版本有 SQL 但某些 Sprint 全前端未触发后端 Step 1、或开发期 DB 曾不可达导致未应用），避免未应用的 SQL 静默流到部署后才炸。

```bash
# ★ 本块自取版本号：flow 分片间 shell 变量不持久，$VERSION 在别处赋值到这里恒空 ——
#   空值会让 SQL_DIR 退化成 "docs/deployment//sql/增量"、用例扫描目录变 "docs/testing/"，
#   进而被误判成"本版无 SQL / 无用例"而整段跳过。
# ⛔ 首选 TARGET_VERSION，`current-version` 只作兜底（根因见 rationale.md「版本号取错」）。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell 2>/dev/null || true)"
VERSION="${TARGET_VERSION:-$(python3 .aidp/scripts/baseline_edit.py current-version)}"
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号（TARGET_VERSION 与 current-version 均空）→ 中止本步，不静默跳过"; exit 1; }
V="$VERSION"; SQL_DIR="docs/deployment/$V/sql/增量"                  # SQL 最终落位（约定 6/§2.5.4）
[ -d "$SQL_DIR" ] || SQL_DIR="code/sql/$V"                      # 兼容 legacy 存量（grandfather）
APPLIED="memory/$V/$(git config user.name)/.applied-sql.json"   # /sprint-dev Step 1 维护的已应用清单
if ls "$SQL_DIR"/[0-9][0-9]_*.sql >/dev/null 2>&1; then
  UNAPPLIED=""
  for f in "$SQL_DIR"/[0-9][0-9]_*.sql; do
    case "$(basename "$f")" in 99_*) continue ;; esac          # 跳过回滚脚本
    # 已应用清单里有该文件名且 sha 未变 → 已应用；否则计入未应用
    if [ ! -f "$APPLIED" ] || ! grep -q "$(basename "$f")" "$APPLIED" 2>/dev/null; then
      UNAPPLIED="$UNAPPLIED $(basename "$f")"
    fi
  done
  if [ -n "$UNAPPLIED" ]; then
    echo "⚠️ 部署阻断风险：本版本以下 SQL 未确认应用到开发库 →$UNAPPLIED"
    echo "   部署后可能表缺失报错。请补跑 /sprint-dev（后端 Phase 1.2 Step 1 会自动应用，约定 6）或手动应用后再部署/测试。"
    # 非阻塞：显式呈现风险即可（记入最终汇总报告「SQL 应用」段）；交互式可 AskUserQuestion 让用户选「先补应用 / 继续」
  else
    echo "✅ 本版本 SQL 均已应用到开发库（.applied-sql.json 覆盖 $SQL_DIR/ 全部 NN_*.sql）"
  fi
fi
```

#### Step 6.0.6 ★ 部署流程文档校验（部署前安全网 — 防「部署先于部署文档」，与 /sprint-dev Step X.8 呼应）

> 本版本若有部署侧变更（sql/ 有脚本 / 部署后回填接口 / 需重启），部署流程 SOP + SQL执行台账应由 `/sprint-dev` **Step X.8（检测驱动）**在开发期已生成。本步是**部署前兜底核验**——堵住边界（某些 Sprint 全前端未触发 / Step X.8 曾被跳过），避免"制品已部署、部署流程文档还不存在"的倒序。

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell 2>/dev/null||true)"; VERSION="${TARGET_VERSION:-$(python3 .aidp/scripts/baseline_edit.py current-version)}"   # 口径同 6.0.5 首处
V="$VERSION"; SQL_DIR="docs/deployment/$V/sql/增量"; [ -d "$SQL_DIR" ] || SQL_DIR="code/sql/$V"
FLOW="docs/deployment/$V/部署流程/部署流程.md"
if ls "$SQL_DIR"/[0-9][0-9]_*.sql 2>/dev/null | grep -qv '99_'; then   # 本版有部署侧变更信号
  if [ ! -f "$FLOW" ] || grep -q '{version}\|{prev-version}' "$FLOW" 2>/dev/null; then
    echo "⚠️ 部署阻断风险：本版有 SQL 但『$FLOW』缺失或仅剩模板占位符。"
    echo "   请补跑 /sprint-dev（Step X.8 检测驱动会从模板 bootstrap 部署流程 + SQL执行台账）后再部署/测试。"
    # 非阻塞：显式呈现（记入最终汇总报告「部署文档」段）；交互式可 AskUserQuestion 让用户选「先补生成 / 继续」；
    # 无人值守（autopilot 调起，已带 --skip-aiauto-test 时不到本步）不弹窗、仅 WARN + 报告留痕
  else
    echo "✅ 本版本部署流程文档已就绪：$FLOW"
  fi
fi
```

#### Step 6.1 测试用例存在性校验（测试人员或研发自测任一存在即可）

`/sprint-aiauto-test` Phase 2.0 用例来源优先级铁律：测试人员为主（`docs/testing/{version}/正式用例/`）+ 研发自测查漏补充（`docs/testing/{version}/研发自测/` 或单文件 `docs/testing/{version}/研发自测.md`）。本步骤只确保至少有一处有用例可读：

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell 2>/dev/null||true)"; VERSION="${TARGET_VERSION:-$(python3 .aidp/scripts/baseline_edit.py current-version)}"   # 口径同 6.0.5 首处
V="docs/testing/$VERSION"

# 测试人员用例：正式用例/ 下排除环境配置 + 待澄清
TEST_TEAM_HAS=$(find "$V/正式用例" "$V/测试验收" "$V/测试执行" -maxdepth 1 -name "*.md" \
  -not -name "_*" \
  -not -name "00*" -not -name "01_测试环境与账号.md" -not -name "99_*" -not -name "README.md" 2>/dev/null | head -1)
# ⛔ 必须排除 `00*`（索引）：否则目录只剩 `00_索引.md` 时本步判「✅ 用例存在」放行，
#    而 aiauto-test 按其单一信源（phase-2-1.md）判零用例 → 累计 env_fail_streak、
#    3 tick 后按 testplan-incomplete 冻结。排除口径以 phase-2-1.md 为准。

# 研发自测用例：研发自测/ 子目录或单文件
DEV_HAS=$(find "$V/研发自测" -maxdepth 2 -name "*.md" -not -name "_*" -not -name "99_*" -not -name "01_测试环境与账号.md" -not -name "01_研发自测方案.md" -not -name "00_研发自测方案.md" -not -name "00_索引.md" -not -name "README.md" 2>/dev/null | head -1)
[ -z "$DEV_HAS" ] && [ -f "$V/研发自测.md" ] && DEV_HAS="$V/研发自测.md"

if [ -n "$TEST_TEAM_HAS" ] || [ -n "$DEV_HAS" ]; then
  echo "✅ 测试用例存在，进 Step 6.2"
  [ -n "$TEST_TEAM_HAS" ] && echo "   → 测试人员用例（正式用例/）：✓"
  [ -n "$DEV_HAS" ] && echo "   → 研发自测用例：✓"
else
  echo "⚠️ 正式用例/ 与 研发自测/ 均无用例，跳过 AI 自动化测试"
  # 报告里标 ⏭️ 已跳过（测试用例缺失，请先跑 /sprint-plan 或 /version 补生成）
  # 不主动调 /sprint-plan：用例缺失时保守跳过 AI 测试并记入报告，不自动补生成用例
  echo "⏭ 跳过 Step 6，直接进入最终汇总报告"
  exit 0   # ⛔ 必须真退出：此处曾写裸词 GOTO_FINAL_REPORT（不存在的命令），
           #    逐字执行 command not found 且其后无 exit，会带着未初始化状态继续往下跑
fi
```

#### Step 6.2 deployment 配置读取与确认

1. **定位 PRD 文件**：扫 `docs/requirements/$VERSION/产品提供/*.md` 取第一份；找不到 → 跳过 + 报告标"PRD 缺失"
2. **抽 YAML frontmatter 中 `autopilot_decisions.deployment` 段**：
   ```bash
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell 2>/dev/null||true)"; VERSION="${TARGET_VERSION:-$(python3 .aidp/scripts/baseline_edit.py current-version)}"   # 口径同 6.0.5
   PRD_FILE=$(ls docs/requirements/"$VERSION"/产品提供/*.md 2>/dev/null | head -1)   # 步骤 1 的"取第一份"落成可执行
   [ -n "$PRD_FILE" ] || { echo "⛔ 未找到 PRD（docs/requirements/$VERSION/产品提供/*.md）→ 跳过本步并在报告标「PRD 缺失」"; }
   DEPLOY_MODE=$(awk '/^---$/{f=!f;next} f && /^[[:space:]]*mode:/{print $2;exit}' "$PRD_FILE")
   ```
3. **分支处理**：
   - **deployment 段完整**（含 mode + 对应 mode 的 URL/等待时长 + 登录段（如需要））→ 用 `AskUserQuestion` 让用户在「**沿用当前配置 / 修改 / 跳过本次 AI 自动化测试**」三选一（命令带 `--auto-aiauto-test` → 直接走"沿用"）
   - **deployment 缺失或字段不全** → 主动用 `AskUserQuestion` **分批收集**（deployment 字段清单以 `/sprint-aiauto-test` Phase 0.3 为单一信源，不在此复述具体字段名），收完写回 PRD 头部 `autopilot_decisions.deployment` 段并 `git add + commit`，commit 消息 `feat({version}): 补充 deployment 配置（sprint-batch Step 6.2）`
   - **deployment.mode == none** → 由 6.0 判定门兜住，本步骤不会到这
   - **★ `--unattended` / `/loop` 无人值守（不弹窗铁律，勿只靠顶部 catch-all）**：deployment 段完整 → 直接"沿用"、不弹窗；字段不全 → 不弹窗收集，按已有字段跑、缺字段标 `{待用户填写}` 占位交测试链路（同 aiauto-test Phase 0.6 无人值守守卫口径），绝不因本步 `AskUserQuestion` 挂起。

> ★ **不调 sprint-aiauto-test 的 Phase 0.3 / sprint-autopilot 的 Phase 0.6**（按约定 21）：sprint-batch 自己用 `AskUserQuestion` 收集后写回 PRD，aiauto-test 跑时直接读取已写入的 deployment 段。

#### Step 6.3 部署完成确认（人在回路）

> ★ **`--unattended` / `/loop` 无人值守（本步整段不弹窗）**：`mode=local` → 假定 dev server 已由部署阶段起（直接进 6.4，未就绪由 aiauto-test 部署探针超时让位、不问人）；`mode=cloud` → 直接进 6.4 让 aiauto-test Phase 1 自探部署就绪；均不弹 `AskUserQuestion`。下方三选一仅**交互式**用。

按 deployment.mode 分流询问（**交互式**）：

- **mode=local**：
  ```
  AskUserQuestion: "是否已在本地启动 dev server？"
  选项 ① 已启动（前端 + 后端都跑起来了）→ 进 6.4
  选项 ② 未启动 → 打印启动建议（基于 deployment.local_frontend_url + local_backend_url 推断 npm run dev / mvn spring-boot:run 等命令），等用户跑完再确认 → 进 6.4
  选项 ③ 现在不跑 AI 自动化测试 → 跳过，标"用户延后"
  ```
- **mode=cloud**：
  ```
  AskUserQuestion: "云端部署状态？"
  选项 ① 已触发 CI/CD 部署且 deploy_check_url 应该已就绪 → 进 6.4（让 aiauto-test Phase 1 自己探测）
  选项 ② 已触发但还在跑 → 进 6.4（aiauto-test 内部最长等 cloud_deploy_check_timeout_seconds）
  选项 ③ 还没触发部署 → 提示用户先触发部署（如 push tag / 调 CI webhook），跳过本轮，记报告"待用户手动 /sprint-aiauto-test --once 跑"
  ```

#### Step 6.4 ~ 6.6

> 📄 **本段全文见 `step-6b.md`**（6.4 baseline 预写 + 调用 `/sprint-aiauto-test --once`、6.5 问题回写「问题汇总清单」、6.6 整体失败兜底）。进入本段第一动作 = Read 该文件。
