<!-- 二次切分 · phase-2 片1/2：覆盖 2.0 用例来源优先级解析（含当前版本验收清单/渲染模式拆分）-->
# sprint-aiauto-test · Phase 2 详情（AI 自动化仿真测试主循环 2.0–2.4）

> 本文件是 `/sprint-aiauto-test` 命令 **Phase 2** 详情的**第 1/2 片**（⛔ 本片不含 Phase 2 全部子步——后续子步在 `-2`…`-2` 分片，按进度依次 Read，勿读完本片即认为已覆盖全段），由命令主体（`{{AIDP_HOME}}/commands/sprint-aiauto-test.md`）在**进入 Phase 2 时用 Read 工具按需加载**。命令主体只保留 Phase 2 的**硬门 + 2.0–2.4 骨架 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入 Phase 2 后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/`。理据/根因见同目录 `rationale.md`。

---

## Phase 2：AI 自动化仿真测试主循环

> **执行内核 = `auto-test-runner`（约定 21）**：命令只组装 run-context、按模块派执行子 Agent、消费结果；执行方先 Read `references/execution-contract-lite.md`，判不准按索引补读端驱动/方法论。不在命令中复刻逐条驱动调用。

> **★ A2 主循环上下文契约（auto-test-runner 是"子 Agent 执行内核"，主循环只读契约摘要、不载全文 SKILL.md）**：`auto-test-runner` SKILL.md 定位就是"给**执行子 Agent** 用的执行内核"（其内明写"子 Agent 必须自己 Read 方法论文件"）——**主循环 `Skill`-invoke 它 = 纯浪费上下文**（把几千行方法论灌进主循环却不在主循环执行）。故：**主循环只按下面 ≤契约摘要 派发子 Agent，完整 SKILL.md 方法论只在被派发的【测试执行子 Agent】自身上下文里加载**：
> - **输入**：run-context（被测端/驱动/URL/账号/等待时长/证据目录/用例集路径）
> - **产物**：`docs/reports/{V}/AI测试报告/`（经 emit-report.py 出 SPA）+ `results/{TC-ID}.json` + `tasks.md`（断点续跑）
> - **落盘/退出码**：模块级 tasks 状态机 `[ ]/[>]/[√]/[!]`；块守恒 / 证据齐全后回传 compact `{module,total,pass,fail,block,evidence_dir,defects[]}`（B3）
> - 主循环**只消费 compact 回传 + 产物路径**，**⛔ 绝不把 auto-test-runner SKILL.md 全文 / 逐条浏览器往返读进自身上下文**（B2 主循环禁区）。

> 🪟 **渲染模式 + 驱动对本主循环透明**：Phase 0 已按 `RENDER_MODE`（默认无头 `--headless=new`）+ `DRIVER`（本地 `cli` / 远程 `mcp`）启动/连接 Chrome；本循环的所有浏览器操作（navigate / click / fill / wait / screenshot / 取控制台错误）**经当前 `DRIVER` 执行**——`DRIVER=cli` 走 `chrome-devtools-cli`、`DRIVER=mcp-remote` 走 chrome-devtools-mcp tool，**两驱动 + 无头/有头下行为完全一致**，截图照常出图（见 3.2.5）。无需为无头 / 为某一驱动改写任何用例步骤；CLI 的具体调用映射详见依赖 SKILL。
> 🟢 **`DRIVER=cli` 下「必须有头」用例同会话即时跑**：本地 CLI 跑到标记「必须有头」的用例时，**重启本机 chrome 切有头（去 `--headless=new`）执行该用例、跑完再切回无头**——仅重启本机 chrome 进程（本地秒级，须重新登录则按登录流程走），**Claude Code 无需重启**，故无需延后（Phase 2.0-E 在 `DRIVER=cli` 时本就不拆延后集）。建议把同角色的「必须有头」用例**聚到一起切一次**减少 chrome 重启次数。仅 `DRIVER=mcp-remote` 远程才延后 + 收敛后提醒（Phase 3.5）。

### 2.0 当前版本完整验收集合（独立实测只用明确目标）

> ⛔⛔ **2.0.0 前置门：本版有没有【未级联】的用例增量**（约定 22 × 本链路交界，先跑再解析来源）
>
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version "$TARGET_VERSION"
> ```
>
> 增量册记的是**变更线索**（一行），不是可执行用例（`SUITE-*`/`TC-*`/四要素步骤表）——
> 把线索变成用例的是**用例族定向级联**（处置 1，产物写进 `02_*.md`）。故 2.0 的用例发现
> **刻意排除 `_*`**，而排除的前提是级联真的跑过了。理据见 `rationale.md`。
>
> - **exit 0** → 正式用例册即完整用例集，照常进 2.0。
> - **exit 1** → 用例义务未齐，返回具体阻塞；测试-only不生成规格/用例、不开发/提交/部署。原开发父任务如有document授权可补齐后重新冻结清单。
> - **exit 2** → 台账/状态不可判读，返回未核验，不能当作无欠账。
> - 补不齐时记录 `case_ledger_pending` 和覆盖不完整结论，停止本轮开测；⛔ 不要把增量册塞进用例发现；不得据此判版本通过，也不能让老用例全绿掩盖新增用例未生成。
>
> ★ **2.0.0bis 算本轮增量用例集**（前置门过后立刻跑；**只给报告用，不改执行范围**）
>
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> python3 {{AIDP_HOME}}/scripts/incremental_cases.py --version "$TARGET_VERSION" --build "$BUILD" --record
> ```
>
> **执行范围仍为当前版本冻结清单及必要依赖**（不发现全项目/历史全集；同内容有效证据可复用）；本步只解决**报告分不清**。
> 判据靠 git 新增的用例标题行、不靠标记，落 `builds[].incremental_case_ids`；
> 无基准判 `no-anchor` + 空集 + 标「全量」。理据见 `rationale.md`。

进入 2.1 主循环之前，先按以下铁律解析"本次跑哪些用例"：

```bash
# ★ 跨分片取回本 tick 变量 —— flow 每个分片是**独立的 Bash 调用**，shell 变量不持久；
#   漏这一行会让下方判据读到空串、`${VAR:-默认}` 静默落默认值（恒真/恒假）。
#   真源在 baseline 的（BUILD/DRIVER/DEPLOY_MODE/NOTIFY_ENABLED/LOOP_UNATTENDED…）由脚本自动回落。
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# 当前版本全量只能来自真实autopilot委派的冻结manifest。
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须继承真实委派child}"
PRIMARY_CASES=$(python3 - "$EXECUTION_CONTEXT" "$TARGET_VERSION" "$BUILD" <<'VERSION_CASES'
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from entry_context import load_context
from execution_policy import validate_test_binding
from build_unit_test import load_plan, validate_case_index, formal_case_books
root = Path.cwd()
ctx = load_context(root, sys.argv[1], migrate=False)
validate_test_binding(root, ctx, sys.argv[2], sys.argv[3])
plan = json.loads(Path(ctx["test_manifest"]["path"]).read_text())
load_plan(root, sys.argv[2], sys.argv[3], plan["commit"], plan)
ids = set(validate_case_index(root, plan))
TS = "{{AIDP_HOME}}/skills/auto-test-runner/scripts/tasks_state.py"
def book_ids(book):  # tasks_state.py ids：只读列出册内用例 ID，不建 tasks.md、不构成执行范围
    out = subprocess.run([sys.executable, TS, "ids", str(book), "--json"], check=True, capture_output=True, text=True)
    return {item["id"] for item in json.loads(out.stdout)["cases"]}
for path in formal_case_books(root, sys.argv[2]):  # 与 validate_case_index 共用同一排除规则
    selected = book_ids(path)
    if selected & ids:
        if not selected <= ids:
            raise SystemExit("UNVERIFIED: 用例册含未授权ID")
        print(path.relative_to(root))
VERSION_CASES
) || exit $?
[ -n "$PRIMARY_CASES" ] || { printf '%s\n' 'UNVERIFIED: 当前版本完整用例清单缺失'; exit 2; }
SUPPLEMENT_CASES=""
SUPPLEMENT_UNIQUE=""
CASE_SOURCE_MODE="当前版本冻结验收清单"
# 必要回归依赖仅从manifest.dependencies消费；不自动并入历史[回归]册。

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
  NEW_PRIMARY=""
  for f in $PRIMARY_CASES;    do is_headed_only "$f" && DEFERRED_HEADED_CASES="$DEFERRED_HEADED_CASES $f" || NEW_PRIMARY="$NEW_PRIMARY $f"; done
  NEW_SUPP=""
  for f in $SUPPLEMENT_UNIQUE; do is_headed_only "$f" && DEFERRED_HEADED_CASES="$DEFERRED_HEADED_CASES $f" || NEW_SUPP="$NEW_SUPP $f"; done
  PRIMARY_CASES="$NEW_PRIMARY"; SUPPLEMENT_UNIQUE="$NEW_SUPP"     # 本轮实跑集已剔除「必须有头」
  [ -n "$DEFERRED_HEADED_CASES" ] && echo "🪟 远程无头本轮延后 $(echo $DEFERRED_HEADED_CASES | wc -w) 条「必须有头」用例 → 无头闭环收敛后由 Phase 3.5 一次性提醒切有头补跑（远程绝不中途切，见 0.1.1.5③）"
fi
# ★ 立即落盘（勿删）：消费点 Phase 3.5（phase-3-4.md 的 `[ -z "$DEFERRED_HEADED_CASES" ]`）在**别的分片**、
#   属另一次 Bash 调用，shell 变量不跨调用存活；BASELINE_FALLBACK 指向的 version:deferred_headed_cases
#   **全仓无写入者**，不落盘则读回恒空 → 延后集永远判为空 → 「切有头补跑」的提醒永不触发，
#   那批「必须有头」用例就此静默消失（报告里看不出漏测）。
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test DEFERRED_HEADED_CASES "${DEFERRED_HEADED_CASES:-}"
# DRIVER=cli（本地）：不拆延后集，「必须有头」用例同会话即时切有头跑（CLI 免重启）
# RENDER_MODE=headed（已整体有头）：全部用例本轮都能跑，DEFERRED_HEADED_CASES 为空、无延后
```

> ★ 报告写法（Phase 3）：主集与补集**分两段**呈现 — 「① 主集用例（来源：测试人员）」+ 「② 补集用例（来源：研发自测查漏）」；执行顺序为主集 → 补集；若主集 = 研发自测唯一来源，则只输出单段。**仅 `DRIVER=mcp-remote` 远程无头模式下，被 E 段拆出的「必须有头」用例不计入本轮主/补集执行，仅在 Phase 3.5「待覆盖」段列出；`DRIVER=cli` 本地则全部计入本轮（含必须有头）。**

### 2.0.7 ★ 前置数据体检门（P0-6 — 前置数据缺则整批 block，不逐条跑到一半才发现）

**动机**：实测某轮 47 条阻塞绝大多数是同一根因（测试企业只有 1 名员工、每规格只有 1 张订单），却分散在 3 小时里被逐条发现。探测与归因由 `auto-test-runner` 在**开跑前的前置阶段**一次性完成（`references/execution-methodology.md`「一·补」，按 `ED-NNN` 归组），命令端**只传前置项、消费回传、打印**，⛔ 不自建探测、不批量调 API/DB、不做三态归因（约定 21）。

**步骤**：
1. **汇总前置数据需求并交 run-context**：扫本轮用例集每条的「前置数据编排」段 + `docs/testing/{version}/研发自测/01_研发自测方案.md` §3.3「前置数据准备」，汇总出本轮全部前置数据项（如：≥2 张同规格订单 / ≥5 名员工 / 第二企业账号…）及其依赖用例集合，连同数据面入口（run-context `datasource`，须先过归属校验，见上游 `references/execution-methodology.md`「十一、数据源归属校验」）一并写入 run-context。用例侧须有结构化 `ED-NNN` 前置探测声明才走 SKILL 前置阶段；只有自然语言前置的用例按旧流程由浏览器内感知处理，**SKILL 明令不得据自然语言擅自猜测探测式**。
2. **判定与落 block 归 SKILL**：三态口径（满足 → 进浏览器 / 满足但数据不足 → `block(precondition-unmet)` / 探测本身失败 → `block(network-error|env-unavailable)`）以 SKILL 为单一信源；**⛔ 探测失败绝不得转写成「0 条」或前置不足**——上游硬门 `check_result.py` 的 C13 `probe_error_disguised_as_unmet` 判 Critical，会经 Phase 3.1 形状硬门把整份报告标为证据不合契约。
3. **消费 SKILL 回传后打印体检表**：前置阶段结果落在各 `results/*.json` 的 `precondition_probe.status`（`satisfied` / `unmet` / `probe-error`）与 `block_reason`；命令端只读这些回传字段汇总打印（可执行 / 前置不足 / 探测失败各计数 + 缺失前置清单及受阻用例数），`probe-error` 单列、不计入前置不足。首批结果落盘即可打印，让人在测试早期就知道要补什么数据。
4. **落 run-context + 报告**：体检结果写 run-context「前置数据体检」区；Phase 3 报告「测试概况」引用（各计数 + 缺失清单），#F 通知阻塞数附体检缺失摘要。

**边界**：本门**只传递与消费、不探测、不造数**（造数是「前置数据编排」段 `SQL造删数` 的职责，且受运行时验证纪律约束）；探测失败的归因**以 SKILL 三态为准**，不因探测失败中断整轮。无人值守下全自动、不弹窗。