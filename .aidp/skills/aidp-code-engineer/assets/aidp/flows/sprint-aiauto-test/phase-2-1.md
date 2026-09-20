<!-- 二次切分 · phase-2 片1/2：覆盖 2.0 用例来源优先级解析（含跨版本回归继承/渲染模式拆分）-->
# sprint-aiauto-test · Phase 2 详情（AI 自动化仿真测试主循环 2.0–2.4）

> 本文件是 `/sprint-aiauto-test` 命令 **Phase 2** 详情的**第 1/2 片**（⛔ 本片不含 Phase 2 全部子步——后续子步在 `-2`…`-2` 分片，按进度依次 Read，勿读完本片即认为已覆盖全段），由命令主体（`.aidp/commands/sprint-aiauto-test.md`）在**进入 Phase 2 时用 Read 工具按需加载**。命令主体只保留 Phase 2 的**硬门 + 2.0–2.4 骨架 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入 Phase 2 后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/`。理据/根因见同目录 `rationale.md`。

---

## Phase 2：AI 自动化仿真测试主循环

> ⛔ **执行内核委派 `auto-test-runner` skill（单一信源，约定 21）**：本 Phase 的**用例执行方法论**——分模块批量调度、模块内一次登录共享会话、感知-执行-校验-决策闭环、执行模式分级（详见 skill）、失败分级不中断、进度断点恢复（tasks.md 状态机）、证据取证——**全部沉淀在 `auto-test-runner` skill，命令端不复述、不手写逐条 chrome 调用**。命令端只做三件事：① **组装 run-context**（被测端/驱动/URL/账号/等待时长/证据目录/用例集，见 2.0.5）→ ② **按模块派「测试执行子 Agent」**（`Agent`/Task 工具；prompt 只给 SKILL.md + 方法论文件路径 + 用例路径 + run-context 路径，子 Agent 自行 `Read`，见 2.0.5）→ ③ **消费其产物**（`results/{TC-ID}.json` + `tasks.md` + 固定结构报告）做 AIDP 特有后处理（运行时错误升级 bug 见 2.4、AI测试报告 HTML 见 Phase 3、里程碑通知）。`phase-2-2.md` 的 2.1/2.2 浏览器操作细节均为 **skill 内部行为示意**（帮助理解 skill 在做什么），**命令端不再自己直驱浏览器**；chrome-devtools-mcp 作为 auto-test-runner 「Web 端驱动适配器」的具体驱动被 skill 调用（本地 `cli`/远程 `mcp` 前缀仍按 Phase 0.1 定）。

> **★ A2 主循环上下文契约（auto-test-runner 是"子 Agent 执行内核"，主循环只读契约摘要、不载全文 SKILL.md）**：`auto-test-runner` SKILL.md 定位就是"给**执行子 Agent** 用的执行内核"（其内明写"子 Agent 必须自己 Read 方法论文件"）——**主循环 `Skill`-invoke 它 = 纯浪费上下文**（把几千行方法论灌进主循环却不在主循环执行）。故：**主循环只按下面 ≤契约摘要 派发子 Agent，完整 SKILL.md 方法论只在被派发的【测试执行子 Agent】自身上下文里加载**：
> - **输入**：run-context（被测端/驱动/URL/账号/等待时长/证据目录/用例集路径）
> - **产物**：`docs/reports/{V}/AI测试报告/`（经 emit-report.py 出 SPA）+ `results/{TC-ID}.json` + `tasks.md`（断点续跑）
> - **落盘/退出码**：模块级 tasks 状态机 `[ ]/[>]/[√]/[!]`；块守恒 / 证据齐全后回传 compact `{module,total,pass,fail,block,evidence_dir,defects[]}`（B3）
> - 主循环**只消费 compact 回传 + 产物路径**，**⛔ 绝不把 auto-test-runner SKILL.md 全文 / 逐条浏览器往返读进自身上下文**（B2 主循环禁区）。

> 🪟 **渲染模式 + 驱动对本主循环透明**：Phase 0 已按 `RENDER_MODE`（默认无头 `--headless=new`）+ `DRIVER`（本地 `cli` / 远程 `mcp`）启动/连接 Chrome；本循环的所有浏览器操作（navigate / click / fill / wait / screenshot / 取控制台错误）**经当前 `DRIVER` 执行**——`DRIVER=cli` 走 `chrome-devtools-cli`、`DRIVER=mcp-remote` 走 chrome-devtools-mcp tool，**两驱动 + 无头/有头下行为完全一致**，截图照常出图（见 3.2.5）。无需为无头 / 为某一驱动改写任何用例步骤；CLI 的具体调用映射详见依赖 SKILL。
> 🟢 **`DRIVER=cli` 下「必须有头」用例同会话即时跑**：本地 CLI 跑到标记「必须有头」的用例时，**重启本机 chrome 切有头（去 `--headless=new`）执行该用例、跑完再切回无头**——仅重启本机 chrome 进程（本地秒级，须重新登录则按登录流程走），**Claude Code 无需重启**，故无需延后（Phase 2.0-E 在 `DRIVER=cli` 时本就不拆延后集）。建议把同角色的「必须有头」用例**聚到一起切一次**减少 chrome 重启次数。仅 `DRIVER=mcp-remote` 远程才延后 + 收敛后提醒（Phase 3.5）。

### 2.0 用例来源优先级解析（★ 测试人员为主 + 研发自测查漏补充）

> ⛔⛔ **2.0.0 前置门：本版有没有【未级联】的用例增量**（约定 22 × 本链路交界，先跑再解析来源）
>
> ```bash
> eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> python3 .aidp/scripts/check_case_ledger_pending.py --version "$TARGET_VERSION"
> ```
>
> 增量册记的是**变更线索**（一行），不是可执行用例（`SUITE-*`/`TC-*`/四要素步骤表）——
> 把线索变成用例的是**用例族定向级联**（处置 1，产物写进 `02_*.md`）。故 2.0 的用例发现
> **刻意排除 `_*`**，而排除的前提是级联真的跑过了。理据见 `rationale.md`。
>
> - **exit 0** → 正式用例册即完整用例集，照常进 2.0。
> - **exit 1（有 N 条未级联）** → ⛔ **此刻测的是【老用例集】，全绿也不代表新功能被测过**。按序处置：
>   1. **先补级联**：派子 Agent 跑 `/sprint-selftest --ledger-cascade --scale=S [--unattended]`，
>      成功 → 复跑本门 → 进 2.0；
>   2. 跑不动 → **不静默继续**：落 `versions.{V}.case_ledger_pending=N`，报告「测试概况」
>      **必须**标注 `⚠️ 覆盖不完整：N 条用例增量未级联`，且**⛔ 不得据此判版本通过**。
> - **exit 2（读数不可用）** → fail-closed，同 exit 1 处置 2，不假装无未级联。
>
> ⛔ **不要把增量册塞进用例发现来"解决"这个问题**：它解析不出任何 `SUITE-*`/`TC-*`，
> 收进来只静静贡献 0 条用例——把"没测"伪装成"测了"，比现在更糟。

> ★ **2.0.0bis 算本轮增量用例集**（前置门过后立刻跑；**只给报告用，不改执行范围**）
>
> ```bash
> eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> python3 .aidp/scripts/incremental_cases.py --version "$TARGET_VERSION" --build "$BUILD" --record
> ```
>
> **执行仍全量**（每轮从整个用例集重建 tasks.md，⛔ 不按增量裁剪）；本步只解决**报告分不清**。
> 判据靠 git 新增的用例标题行、不靠标记，落 `builds[].incremental_case_ids`；
> 无基准判 `no-anchor` + 空集 + 标「全量」。理据见 `rationale.md`。

进入 2.1 主循环之前，先按以下铁律解析"本次跑哪些用例"：

```bash
# ★ 跨分片取回本 tick 变量 —— flow 每个分片是**独立的 Bash 调用**，shell 变量不持久；
#   漏这一行会让下方判据读到空串、`${VAR:-默认}` 静默落默认值（恒真/恒假）。
#   真源在 baseline 的（BUILD/DRIVER/DEPLOY_MODE/NOTIFY_ENABLED/LOOP_UNATTENDED…）由脚本自动回落。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
V="docs/testing/${TARGET_VERSION}"

# A. 测试人员提供的用例：正式用例/ 下排除 00*（环境/账号/方案/索引等配置）与 99*（待澄清清单）前缀的管家文件，其余全部 .md
#    （按 00/99 前缀约定排除，不写死具体文件名；真正的用例文件从 01_ 起编号）
TEST_TEAM_CASES=$(find "$V/正式用例" "$V/测试验收" "$V/测试执行" -maxdepth 1 -name "*.md" \
  -not -name "_*" \
  -not -name "00*" \
  -not -name "99*" \
  -not -name "README.md" 2>/dev/null | sort)

# B. 研发自测用例：研发自测/ 下排除管家文件（索引态：00_索引 / 01_研发自测方案 / 01_测试环境与账号 / 99_待澄清 / 旧锚 00_研发自测方案），用例从 02_ 起
#    （口径对齐 `sprint-test.md` 用例文件筛选那段的 `-not -name "99_*"`；98_跨系统验证清单是 auto-test-runner 的用例源，不排除；旧锚 grandfather 布局的 01_ 用例仍纳入——旧锚下 00_ 才是方案、01_ 是用例，不误排）
DEV_CASES=$(find "$V/研发自测" -maxdepth 2 -name "*.md" \
  -not -name "_*" \
  -not -name "00_索引.md" \
  -not -name "00_研发自测方案.md" \
  -not -name "01_研发自测方案.md" \
  -not -name "01_测试环境与账号.md" \
  -not -name "99_*" \
  -not -name "README.md" 2>/dev/null | sort)
[ -z "$DEV_CASES" ] && [ -f "$V/研发自测.md" ] && DEV_CASES="$V/研发自测.md"

# B2. ★ 跨版本回归用例继承（约定33 缺口5.2）：并入【历史版本】研发自测/ 中标 [回归] 的用例，
#     让 /sprint-bugfix 缺陷反哺生成的回归用例跨版本沉淀、每版 release 自动复跑历史回归集（不从零开始）。
#     标记来源：正文/frontmatter 含「[回归]」「回归用例」「关联缺陷:」任一（由 dev-manual-testcase 产出、bugfix 反哺时打标）。
#     注：[回归] 标记 + 关联缺陷字段由 dev-manual-testcase 产出（见其用例模板 + check_testcase_format），本 glob 直接消费。
REGRESSION_CASES=$(
  for d in $(find docs/testing -maxdepth 2 -type d -name "研发自测" 2>/dev/null | sort); do
    case "$d" in *"/${TARGET_VERSION}/"*) continue;; esac   # 跳过当前版本（已在 DEV_CASES）
    find "$d" -maxdepth 2 -name "*.md" -not -name "_*" -not -name "00_*" -not -name "01_研发自测方案.md" -not -name "01_测试环境与账号.md" -not -name "README.md" 2>/dev/null
  done | while read -r f; do grep -qiE '\[回归\]|回归用例|关联缺陷[:：]' "$f" 2>/dev/null && echo "$f"; done | sort -u
)
[ -n "$REGRESSION_CASES" ] && echo "♻️  并入跨版本历史回归用例 $(echo $REGRESSION_CASES | wc -w) 条（约定33 缺口5.2：缺陷反哺回归集跨版本继承）"

# C. 优先级判定
if [ -n "$TEST_TEAM_CASES" ]; then
  echo "🎯 检测到测试人员用例 → 主集"
  PRIMARY_CASES="$TEST_TEAM_CASES"
  SUPPLEMENT_CASES="$DEV_CASES"   # 研发自测作为查漏补充
  CASE_SOURCE_MODE="测试人员为主 + 研发自测查漏补充"
elif [ -n "$DEV_CASES" ]; then
  echo "🎯 未检测到测试人员用例 → 研发自测兜底"
  PRIMARY_CASES="$DEV_CASES"
  SUPPLEMENT_CASES=""
  CASE_SOURCE_MODE="研发自测唯一来源"
else
  # ⛔ 无可用用例 = 确定性阻塞，不能只 echo+exit（每 tick 撞同一处、无 #4/streak/冻结 = 静默空转）。
  #    ⛔ 专属 case_gate_fail_streak，不复用 env_fail_streak（0.1.1 通过即清零它 ⇒ 本门阈值恒不可达）。
  #    达阈或无唤醒源即按「冻结字段写入契约」冻结
  #    （**配置类**：解冻看用例/测试方案 mtime）。根因见 rationale.md。
  echo "❌ 正式用例/ 与 研发自测/ 均无可用用例 → 本 tick 不测"
  echo "   → 补用例：/sprint-selftest，或放进 正式用例/"
  # 记账→判阈（内含无唤醒源即当场达阈）→冻结四件套→发 #4，一次做完
  python3 .aidp/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
    --phase 2.0-cases --reason testplan-incomplete \
    --streak-key case_gate_fail_streak --threshold "${ENV_FAIL_FREEZE_THRESHOLD:-3}" \
    --why "正式用例/ 与 研发自测/ 均无可用用例，连续多 tick 无法开测；补用例即自动解冻"
  exit 0   # ⛔ 不用 exit 1：已记账 + 已告警，让位本 tick 而非让 /loop 每 tick 撞同一失败
fi
# ★ 有可用用例 → 清零环境熔断计数
python3 .aidp/scripts/baseline_edit.py --version "$TARGET_VERSION" del case_gate_fail_streak || true

# ★ 跨版本回归用例并入补充集（约定33 缺口5.2），随后随补充集统一去重（历史回归与本版用例撞功能点则去重保留其一）
[ -n "$REGRESSION_CASES" ] && SUPPLEMENT_CASES=$(printf '%s\n%s\n' "$SUPPLEMENT_CASES" "$REGRESSION_CASES" | sed '/^$/d' | sort -u)

# D. 去重（按功能点 ID / 用例 ID 标识）：SUPPLEMENT_CASES 中已被 PRIMARY_CASES 覆盖的功能点直接跳过
#    标识抽取规则：用例文件 frontmatter 或正文中的「功能点 ID」/「关联功能点」/「REQ-{version}-NNN」字段
#    具体去重算法见 SKILL 内部 (dev-manual-testcase 输出用例时按 REQ 编号体系标注)
# 纯 shell 去重：补充集中**文件名**已出现在主集里的条目剔除，其余条目**保留完整路径**（含版本目录，
#   下游 is_headed_only / 子 Agent 都按路径读文件）；补充集内部按完整路径去重，不同版本的同名册各自保留。
SUPPLEMENT_UNIQUE=$(awk 'NR==FNR { n=$0; sub(/.*\//, "", n); seen[n]=1; next }
  { n=$0; sub(/.*\//, "", n); if (!(n in seen) && !($0 in kept)) { kept[$0]=1; print } }' \
  <(printf '%s\n' $PRIMARY_CASES | sed '/^$/d') \
  <(printf '%s\n' $SUPPLEMENT_CASES | sed '/^$/d'))

# E. ★ 渲染模式拆分（仅 DRIVER=mcp-remote 远程才拆延后集）：
#    远程 MCP 切模式须重启（0.1.1.5），故无头跑时把「必须有头」用例拆出为延后集，本轮不跑，留到无头闭环收敛后由 Phase 3.5 提醒切有头补跑。
#    本地 DRIVER=cli 免重启即时切：不拆延后集，「必须有头」用例当条切有头 flag 同会话跑掉（见 Phase 2 主循环 🟢 说明）。
#    标记来源：用例文件 frontmatter / 正文含「渲染模式: 有头」「必须有头」「仅有头」「[有头]」任一（测试人员 / 研发自测在用例里显式标）
#    典型「必须有头」场景：图形验证码识别 / 视觉像素级比对 / 文件下载系统弹窗 / 需被网站当真人的反爬交互
DEFERRED_HEADED_CASES=""
# ⛔ 用前缀匹配而非全等："配置期绑定、运行时切不动"对 **两个 MCP 变体**（mcp-remote /
#    mcp-plugin-fallback）都成立；写死某一个会让另一变体漏拆延后集、跑到必须有头的用例才卡住。
case "${DRIVER}" in mcp*) IS_MCP=1 ;; *) IS_MCP=0 ;; esac
if [ "$IS_MCP" = "1" ] && [ "${RENDER_MODE:-headless}" = "headless" ]; then
  is_headed_only() { grep -qiE '渲染模式[:：][[:space:]]*有头|必须有头|仅有头|\[有头\]' "$1" 2>/dev/null; }
  NEW_PRIMARY=""; for f in $PRIMARY_CASES;    do is_headed_only "$f" && DEFERRED_HEADED_CASES="$DEFERRED_HEADED_CASES $f" || NEW_PRIMARY="$NEW_PRIMARY $f"; done
  NEW_SUPP="";    for f in $SUPPLEMENT_UNIQUE; do is_headed_only "$f" && DEFERRED_HEADED_CASES="$DEFERRED_HEADED_CASES $f" || NEW_SUPP="$NEW_SUPP $f"; done
  PRIMARY_CASES="$NEW_PRIMARY"; SUPPLEMENT_UNIQUE="$NEW_SUPP"     # 本轮实跑集已剔除「必须有头」
  [ -n "$DEFERRED_HEADED_CASES" ] && echo "🪟 远程无头本轮延后 $(echo $DEFERRED_HEADED_CASES | wc -w) 条「必须有头」用例 → 无头闭环收敛后由 Phase 3.5 一次性提醒切有头补跑（远程绝不中途切，见 0.1.1.5③）"
fi
# ★ 立即落盘（勿删）：消费点 Phase 3.5（phase-3-4.md 的 `[ -z "$DEFERRED_HEADED_CASES" ]`）在**别的分片**、
#   属另一次 Bash 调用，shell 变量不跨调用存活；BASELINE_FALLBACK 指向的 version:deferred_headed_cases
#   **全仓无写入者**，不落盘则读回恒空 → 延后集永远判为空 → 「切有头补跑」的提醒永不触发，
#   那批「必须有头」用例就此静默消失（报告里看不出漏测）。
python3 .aidp/scripts/autopilot_tick_flags.py set --command aiauto-test DEFERRED_HEADED_CASES "${DEFERRED_HEADED_CASES:-}"
# DRIVER=cli（本地）：不拆延后集，「必须有头」用例同会话即时切有头跑（CLI 免重启）
# RENDER_MODE=headed（已整体有头）：全部用例本轮都能跑，DEFERRED_HEADED_CASES 为空、无延后
```

> ★ 报告写法（Phase 3）：主集与补集**分两段**呈现 — 「① 主集用例（来源：测试人员）」+ 「② 补集用例（来源：研发自测查漏）」；执行顺序为主集 → 补集；若主集 = 研发自测唯一来源，则只输出单段。**仅 `DRIVER=mcp-remote` 远程无头模式下，被 E 段拆出的「必须有头」用例不计入本轮主/补集执行，仅在 Phase 3.5「待覆盖」段列出；`DRIVER=cli` 本地则全部计入本轮（含必须有头）。**

### 2.0.7 ★ 前置数据体检门（P0-6 — 跑用例【前】批量探测前置数据，缺则整批 block，不逐条跑到一半才发现）

**动机**：用例集选定后直接逐条执行、前置数据是否具备全无前置校验。实测某轮 47 条阻塞绝大多数是同一根因（测试企业只有 1 名员工、每规格只有 1 张订单），却分散在 3 小时里被逐条发现——用 2 次 API 调用在开跑前就能查出。故在用例集确定（2.0）后、委派执行（2.1）前插入本门。

**步骤（命令端只做汇总 + 打印 + 落 run-context；探测执行归 SKILL）**：
1. **汇总前置数据需求**：扫本轮用例集每条的「前置数据编排」段 + `docs/testing/{version}/研发自测/01_研发自测方案.md` §3.3「前置数据准备」，汇总出本轮全部前置数据项（如：≥2 张同规格订单 / ≥5 名员工 / 已过期订单 / 第二企业账号…），每项关联「依赖它的用例集合」。
2. **最少调用批量探测**：对每一项用**最少的 API/DB 调用**探测是否具备（同类合并、能一次查全不拆多次；"员工数"一次列表接口即得、"某规格订单数"一次查询即得）。探测走已登录会话的项目自身接口 / run-context `datasource`（datasource 须先过归属校验，见上游 `references/execution-methodology.md`「十一、数据源归属校验」）。
3. **判定与落 block 归 SKILL 执行内核**（约定 21）：`auto-test-runner` 已把「前置数据面探测」
   收进**方法论层第二步前置阶段**（`references/execution-methodology.md`「一·补」），命令端
   **只把前置项与数据面入口作为 run-context 传下去**，⛔ 不自建探测执行与三态归因。
   三态口径（满足 → 进浏览器 / 满足但数据不足 → `block(precondition-unmet)` / 探测本身失败 →
   `block(network-error|env-unavailable)`）以 SKILL 为单一信源；**⛔ 探测失败绝不得转写成
   "0 条"或前置不满足**——上游硬门 `check_result.py` 的 **C13 `probe_error_disguised_as_unmet`
   判 Critical**，会经 Phase 3.1 的形状硬门把整份报告标为证据不合契约。
   ⚠️ 用例侧须有结构化 `ED-NNN` 前置探测声明才走本阶段；只有自然语言前置的用例按旧流程
   由浏览器内感知处理，**SKILL 明令不得据自然语言擅自猜测探测式**。

4. **先打印体检表**：委派执行前终端先打印，让人在**测试开始时**就知道要补什么数据、而非 3 小时后：
   ```
   🩺 前置数据体检（本轮 109 条）：可执行 62 / 前置不足 47
      缺失前置：① 同规格第 2 张订单（阻塞 SUITE-ORDER 的 23 条）② 第 5 名员工（阻塞 SUITE-STAFF 的 18 条）③ 已过期订单（阻塞 6 条）
      → 补齐上述数据后重跑可解除阻塞；本轮先跑 62 条可执行用例
   ```
5. **落 run-context + 报告**：体检结果写 run-context「前置数据体检」区；Phase 3 报告「测试概况」引用（可执行 / 前置不足计数 + 缺失清单），#F 通知阻塞数附体检缺失摘要。

**边界**：本门**只探测、不造数**（造数是「前置数据编排」段 `SQL造删数` 的职责，且受运行时验证纪律约束）；探测失败的归因**以 SKILL 三态为准**（`block(network-error|env-unavailable)`，⛔ 不得写成 `precondition-unmet`），不因探测失败中断整轮。无人值守下全自动、不弹窗。

