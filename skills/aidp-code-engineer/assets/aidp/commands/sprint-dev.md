# /sprint-dev — 开发阶段（独立可用；默认 light，formal 由父编排累进）

## 执行身份与授权前置路由（先于本文其余动作）

先 Read `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`。按原参数解析父上下文与显式 Sprint；历史计划和 activeContext 不决定本任务身份。

`POLICY_ARGS` 仅新任务按 `light-context.md`「入口、继承与 grant revision」生成；嵌套只继承，后文每个动作先过该片围栏。

```bash
# EXECUTION_CONTEXT 来自入参；EXPLICIT_SPRINT 仅来自用户明确的 Sprint，不读 activeContext 推导。
CONTEXT_ARGS=()
if [ -n "${EXECUTION_CONTEXT:-}" ]; then
  CONTEXT_ARGS+=(--execution-context "$EXECUTION_CONTEXT")
else
  CONTEXT_ARGS+=(--version "{version}" "${POLICY_ARGS[@]}")
  for W in "${TASK_WRITE_SET[@]}"; do CONTEXT_ARGS+=(--write-set "$W"); done
  for AC in "${TASK_ACCEPTANCE[@]}"; do CONTEXT_ARGS+=(--acceptance "$AC"); done
  [ -z "${EXPLICIT_SPRINT:-}" ] || CONTEXT_ARGS+=(--sprint "$EXPLICIT_SPRINT")
fi
CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . --entry sprint-dev \
  "${CONTEXT_ARGS[@]}" --json) || exit $?
EXECUTION_CONTEXT=$(printf '%s' "$CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
# 消费 resolve 返回的 execution_context 为 EXECUTION_CONTEXT，再路由。
python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . --entry sprint-dev \
  --execution-context "$EXECUTION_CONTEXT" --phase dev --json
```

返回 `route=light` → 执行该片的 **dev** 能力，然后 **return**；不进入下文任何 Sprint 取号、卡片、activeContext、started、报告路径或归档步骤。返回 `route=formal` 才执行下文正式身份门；可选动作仍按 actions 筛选，未授权为 NOT_REQUESTED。任何子命令/修复/重试/续跑均保留原参数并显式附 `--execution-context "$EXECUTION_CONTEXT"`；不能只传 `--unattended`/`--from-batch` 而丢身份。

## formal 流程

你正在执行 `/sprint-dev` 命令。

**formal 分支支持两种调用分支**（light 已在前置路由返回）
- **分支 A（明确 Sprint）**：`/sprint-full` / `/sprint-batch` 内部调用或用户指定 Sprint，执行该 Sprint 的开发
- **分支 B（明确正式累进）**：formal 父编排明确要求新 Sprint，完成后仅串联父授权的能力；普通描述直接调用仍为 light

**本命令按父授权编排**：默认实现+静态验证+related-test，自动测试与必要修复复验；review、full-cvl、document/docs-audit 逐项过 `light-context.md` 动作围栏。角色写集隔离，已授权检查复用既有证据，修复只复核 delta。权威协议 = `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`。

参数：$ARGUMENTS
- `/sprint-dev` — 有 formal 父上下文时开发其明确 Sprint；独立无上下文时为 light
- `/sprint-dev 001` — 开发已规划的 Sprint-001（前提：已 /sprint-start）
- `/sprint-dev "新增用户导出功能"` — 独立调用为 light；formal 无号父编排内才走新 Sprint 累进
- `/sprint-dev backend` — 仅后端开发（当前 Sprint）
- `/sprint-dev frontend` — 仅前端开发（当前 Sprint）
- `/sprint-dev "<描述>" backend` — 独立调用为 light + 仅后端（formal 无号父编排内才累进新 Sprint）
- `/sprint-dev 001 skip-test` — 跳过后续 test/bugfix/close 自动串联
- `--cascade-now` — ★ **跳过攒批、当场跑完约定 22 四级级联**（默认行为是把变更按族记入 `_开发期{族}增量.md`、留到收口点批量级联，见 `flows/sprint-dev/postdev-writeback-1.md` 步骤 3.8 + `{{AIDP_HOME}}/reference/开发期族增量.md`）。用于**当轮就要拿到自测用例**的场景——收口点不含 `/sprint-close`，当天开发当天关闭的 Sprint 靠它兜底
- `--aiauto-test-required` — 内部编排/用户明确要实测时传递：本轮必须生成正式用例；不启动浏览器，也不代表测试已完成。
- `--skip-aiauto-test` — 外层未安排实测时透传；没有 `--aiauto-test-required` 则将用例生成义务登记到增量册，测试入口再补齐。
- `--dev-scale=S|M|L` — 显式覆盖普通体量档位：S=契约卡＋受影响四族台账；M=契约卡先放行、代码与 docs 按写集并行、test 前完整文档汇合；L=先完整文档后开发。新表/破坏性契约的 L 前置门不能被降档绕过。开发前生产 `dev_scale`，开发后 Step X.0.0 按实际范围复核，`sup_scale` 同步同一 tier。档位只伸缩承载与时机，需求/用例覆盖义务、约定 22/34 及所有适用检查项均保留，详见 `flows/sprint-dev/incremental-contract.md`。
- `--unattended` — ★ autopilot `/loop` 无人值守标记：Step 0 UI 门（C/D）、**Phase 0A.5 死代码决策门情形 C**、Step X.0.0 约定22 级联门、**约定28 引新库同意门**均**不弹 `AskUserQuestion`**，改**消费 PRD `autopilot_decisions` 预声明**（visual_baseline → A/B/C/D；约定22 默认自动级联；死代码情形 C 默认「① 并存切流量」；需引新库无栈支持 → 转失败处置熔断而非弹窗），避免 7×24 挂死（由 `/sprint-autopilot` → `/sprint-batch` → 本命令透传）
- `--from-batch` — 批量子任务标志（由 `/sprint-full` 透传）：本命令不弹 `AskUserQuestion`，内容决策门按「⏸ 待裁决」返回上层（语义单一信源 = `/sprint-full` 参数表）
  - ⛔ **`--unattended` 绝不弹任何交互门（catch-all，覆盖所有未枚举门）**：上面点名的 4 个门只是**举例**，不是穷举白名单。在 `--unattended` 下，**除本命令文档明确写出的「失败/熔断转人工」路径外，严禁 `AskUserQuestion`、严禁以任何形式停下征询用户**。**尤其严禁自发弹出「开发工作量较大 / 如何推进 / 我全自主完成 vs 先做某 Sprint 阶段确认 / 是否继续 / 要不要分阶段」这类范围·进度确认门**——本 Sprint（含累进产生的多个 Sprint）的全部前后端工作是**一个不可分割、必须一次做完的整体**，`--unattended` 只控制交互方式，已授权范围由父策略确定，**不得**以"工作量大 / 稳妥起见"为由降级为分阶段或征询。凡本应由用户拍板处一律走 PRD `autopilot_decisions` 预声明或文档化保守默认；确实无法自动解决的转失败处置（熔断冻结 + 继续/通知，见对应门），**绝不挂起等待用户输入**。

## ⛔ 统一决策纪律（交互式与 `--unattended` 同为硬约束，最高优先）

> 上一条对"自发范围/进度确认门"的禁止**不限于 `--unattended`**——**交互式（用户在场）下同样是硬约束**。无论哪种模式：

- **所有"文档同步 / 是否继续 / 如何推进"的决策，只能走命令文档明确定义的结构化门**（Step 0 UI 门、Phase 0A.5 死代码门、Phase 0B.1.1 完成硬门、Step X.0.0 级联门的破坏性变更确认等）。这些门要么按规则**默认自动执行不弹窗**，要么在**明确枚举的例外**下用 `AskUserQuestion` 给出**固定选项**。
- **严禁 agent 自由发挥式反问**——尤其禁止在开发中途或结尾自发抛出「开发工作量较大 / 要不要补设计文档 / 还是先这样 / 是否继续 / 要不要分阶段」等**非结构化、无预定义选项**的征询。本 Sprint 已授权工作持续完成；document 未授权时跳过成文且不反复询问，已授权则直接完成。
- **交互式与无人值守的唯一差别**：仅在于**明确枚举的结构化门**（如 UI 的 C/D、死代码情形 C、级联的破坏性变更）交互式弹固定选项、无人值守消费 PRD 预声明；**除此之外，两种模式都不得自发停下征询**。凡文档未定义为"该弹窗"的地方，一律按保守默认自动推进。
- **★ 边界澄清：哪些"必须设结构化门"、哪些才是"禁止的自发反问"（防本纪律被误读为"一律别问"而省掉该设的门）**：本纪律禁止的是**无持久副作用、选项不可穷举**的进度/范围征询（"是否继续 / 要不要分阶段 / 要不要补文档 / 工作量大要不要我全自主"）——这些一律按保守默认自动推进、不问。但满足下列**正向判据任一**的动作，**必须**设结构化门（用 `AskUserQuestion` 给固定选项让用户拍板，属**合规的门、不受本纪律"禁自发反问"限制**）：
  1. **会产生持久目录结构**（新建 `docs/{version}/`、`memory/{version}/` 等版本级持久目录）；
  2. **会产生对外承诺**（版本号即 SemVer 兼容性承诺 / git tag / 版本分支等对外制品）；
  3. **不可逆或回退成本高**（已推送的 tag/分支、已分发的制品、`git mv` 一批目录才能撤销的结构）。
  典型如 **Phase 0B.0 版本落点决策门**（三条全中）：**绝不能以"不许自发问"为由跳过**。判定口诀：**动的是"要不要继续/怎么推进"→ 不问自动推进；动的是"版本号/持久目录/对外 tag 这类高成本不可逆承诺"→ 必须设门问用户**。
- **★ "缺陷/问题怎么修"的默认处置 = `/sprint-bugfix`「缺陷处置默认决策纪律」（单一信源，约定 21 不复述）**：开发/修复途中遇到具体缺陷（失败被伪装成成功、前端吞后端 error、上游不可达、上游已交付更优端点、安全 fail-open 等）时，**先问一句「不做这个修复，当前行为是不是错的？」——是→按纪律映射表默认处置【直接修、不问】、拿不准也默认修**；只有"口径/单位/默认值需产品定义""涉及版本号/tag/对外承诺"才归"必须问"。**严禁把本就该默认修的缺陷当成"要产品拍板"挂起等人**（下游反馈根因）。
- **★ 运行时验证纪律 = 约定 35（详规 `{{AIDP_HOME}}/rules/code.md`，约定 21 不复述）**：开发/验证代码**默认静态验证与当前任务相关单测**（类型/语法/lint/确定性脚本）；**绝不为"看 UI 效果 / 验证运行时"擅自启动前后端服务**（`npm run dev`/`vite`/`mvn spring-boot:run` 等——抢端口/冲突/卡机）**或跑完整构建**。需运行时/浏览器验证 → **(a) 已部署环境 / (b) 用户已运行服务（先探端口、有则复用绝不另起）/ (c) 都无先 `AskUserQuestion` 由用户启动**。**★ Bash 起任何常驻服务类命令前先自检**「是否用户显式要求 / 是否 `deployment.mode=local` 授权例外」，否则中止改走 (a)/(b)/(c)。

## 前置流程

**工作分支先决条件**：最外层入口按 `{{AIDP_HOME}}/reference/agent-tools.md`「工作分支：首次选择、项目内沿用」读取 `development.branch_policy`；首次由用户选择并保存，之后沿用。父任务已提供 `task_branch` 时核对并继承，需求累进、修复和子 Agent 不再建分支。未选择的无人值守调用返回 `needs-choice`，不伪造默认选择。本命令的“分支 A/B”是流程路径，不是创建 Git 分支的指令。

**VCS 能力分流（先于任何 Git 命令）**：以 `{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 取得 `vcs_mode=git|none`；`{user}` 以同模块 `developer_identity(Path.cwd())` 解析（显式身份 → 本地 Git 身份 → `AIDP_USER` → OS 用户），不再要求 Git 身份存在。`vcs_mode=none` 时仍执行本地 Sprint 取号、需求/设计/代码开发与静态验证；所有 Git-only 差异、commit、push、CICD 检查分别记 `unsupported:vcs-disabled`（`status=unsupported`，不是 passed），不执行 Git 命令，也不因缺 Git 中止本地开发。Phase 0B.0 的 tag 检测仅适用于 `git`；`none` 时用项目记忆/部署产物等本地发布信号判定，未知发布状态走既有保守版本落点门，绝不把无 Git 等同未发布。后续 `/sprint-test`、`/sprint-close` 沿用同一模式。

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `vcs.py developer_identity(Path.cwd())`（无 Git 也可确定身份）
3. 确认版本规划文档已生成（由 `/version` 完成）

**`vcs_mode=none` 本地文件变更证据（分支 A/B 共用）**：在已确定 `{version}/{user}/{NNN}` 且任何代码删除/改写前拍 `memory/{version}/{user}/sprints/sprint-{NNN}-local-before.json`；分支 A 必须在 Phase 0A.5 前拍，分支 B 在 Phase 0B.2 后、Phase 1 前拍。快照缺失不得把空 diff 判「零变更」，应补从本 Sprint 的逐文件改动记录取得前态；仍无法确认则扩大审计范围而非跳过。每次重入复用原快照，不覆盖开发前态：

```bash
SNAP="memory/{version}/{user}/sprints/sprint-{NNN}-local-before.json"
mkdir -p "$(dirname "$SNAP")"
if [ ! -f "$SNAP" ]; then
  SNAP="$SNAP" VERSION="{version}" python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
roots = [Path("code"), Path("env"), Path("docs/deployment") / os.environ["VERSION"]]
files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
         for root in roots if root.exists() for p in root.rglob("*") if p.is_file()}
Path(os.environ["SNAP"]).write_text(json.dumps(files, ensure_ascii=False, sort_keys=True), encoding="utf-8")
PY
fi
```

回写时读取此快照，重新对相同目录逐文件算 sha256，比较 `before.get(path) != after.get(path)` 取新增/修改文件，`before.keys() - after.keys()` 取删除文件；按相对路径去重，输出确定性变更清单。禁止拿文件 mtime 代替内容哈希或以空 Git diff 当无改动。

## 参数解析与路径分支

```
判断参数第一项：
  - 纯数字（001 / 2）               → 分支 A：开发指定 Sprint（当前 Sprint 必须匹配）
  - backend / frontend / all         → 分支 A：开发当前 Sprint 的指定范围
  - ★ 控制 flag（skip-test / 任何以 `--` 开头的项）
                                     → 不是需求描述：**跳过它继续看下一项**，
                                       全是 flag 就等同「空」→ 分支 A
  - 其余字符串（"xxx"）              → 分支 B：formal 累进新建 Sprint（独立无上下文已在前置路由按 light 返回）
  - 空                                → 分支 A：开发当前 Sprint
```

> ⛔ **控制 flag 那一行不可删**：`/sprint-full` Phase 2 调的就是 `/sprint-dev skip-test [--unattended]`
> （`skip-test` **裸在第一位**）。少了这一行，按上表逐字判定 `skip-test` 属"其余字符串" → 落进
> **分支 B**，于是在编排器已经启动过 Sprint 的情况下再取新号、产 6 类增量文档、
> 并再启动一次新 Sprint。而 `/sprint-full` 落在 `/sprint-batch` 与 autopilot 主链的**每一个
> Sprint** 上。对照 `/sprint-bugfix` 方式 C 传的是 `/sprint-dev {新NNN} skip-test`（数字在前）故不受影响
> ——**只有 `/sprint-full` 这一处是裸传**，本行就是为它写的。

---

## 分支 A：开发已有 Sprint

### Phase 0A：读取上下文

1. 读取 `memory/{version}/{user}/activeContext.md` 获取当前 Sprint 编号（⛔ 该值由 Phase 1.0pre 置位/校验后才可信——batch/autopilot 常绕过 `/sprint-start`，裸读会拿到上一个 Sprint 的编号，进而定错开发范围与死代码扫描范围）
2. 确认设计文档存在（★ **用 glob 探测、兼容约定 14 三态命名**，不硬编码裸名——否则拆分态项目 `01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md` 会被误判"缺文档"而错误中止）：
   - **详细设计**：`ls docs/design/detail/{version}/{00_索引,00_详细设计,01_详细设计,详细设计}.md 2>/dev/null` 任一命中即视为存在（拆分态 `00_索引.md`/`01_详细设计.md` / 单份态 `00_详细设计.md` / 历史存量裸名 `详细设计.md`）
   - **数据库设计 / 接口设计**：同理各按 `{00_数据库设计,02_数据库设计,数据库设计}.md` / `{00_接口设计,03_接口设计,接口设计}.md` glob 探测（拆分态序号不固定，最稳做法 = 直接 `ls docs/design/detail/{version}/*.md` 看是否有内容主文档）
   - `对外开放接口.md`（★ 如本版本有对外开放接口；缺失但 PRD 含对外接口需求 → 提示先跑 `/sprint-design` 补齐）

如果设计目录 `docs/design/detail/{version}/` 无任何内容主文档（`*.md` 仅有 `00_索引`/`99_待澄清` 管家文件或全空），停止并提示用户先执行 `/version` 进行版本规划。

3. **★ GitHub Issue 缺陷读取（可选，仅用户主动提及 GitHub Issue 时，约定 31.3）**：用 `gh issue list` / `gh issue view <编号>` 拉取 → **先预读、理解每条缺陷语义、确认缺陷确实存在/可复现，再纳入本次开发/修复**；缺陷为人工填充不可盲信标题。未主动提及时跳过，不强制拉取；未安装或未登录 `gh` 时终端提示后跳过。

### Phase 0A.5：★ 历史死代码扫描与处置决策门

> **目的**：写码前核实历史同名/同语义实现的可达性与引用。**删除判据唯一信源 = `{{AIDP_HOME}}/rules/code.md` 约定 29「删除证据门」**；Frontend/Backend Agent 的 grep 只提供候选线索，零命中、扫描错误或“重构”字样都不授权删除。只有证据门确认的 B 清单才执行删除，未知一律保留。

**1. 识别本 Sprint 涉及的功能板块**（从设计/需求/计划读取）：

```bash
# 从研发需求 / 详细设计 / 研发执行计划提取本 Sprint 要做的板块/页面/接口名清单
SPRINT_NNN=$(cat memory/{version}/{user}/activeContext.md | grep "当前 Sprint" | awk -F: '{print $2}' | tr -d ' ')
grep -A 50 "Sprint-${SPRINT_NNN}" docs/plans/{version}/01_研发执行计划.md \
  | grep -E "新增|实现|开发|重做|重构" \
  | head -30
# 输出疑似涉及的"业务关键词"清单（如：用户管理、订单导出、报表中心）
```

**2. 收集候选并逐文件核实证据**：读取 Frontend/Backend Agent 核心原则 11 的扫描线索，再按约定 29 核对可达入口、存活引用、动态/外部消费者与连带文件。扫描只完成一部分时不得把未核部分填“无”。

输出 `memory/{version}/{user}/sprints/sprint-{NNN}-deadcode-scan-{YYYYMMDD-HHMM}.md`，删除前必须填写下表（证据列写具体文件:行或调用契约位置）：

| 候选文件 | 本 Sprint 重做依据 | 可达入口证据 | 存活引用/动态消费者证据 | 连带文件独占依据 | 未核项 | 处置 |
|---|---|---|---|---|---|---|
| 每个候选各一行 | 需求/Task 位置 | 有/已证实无/未知 + 证据 | 有/已证实无/未知 + 证据 | 逐文件依据或不删除连带文件 | 必须列全，无则写无 | 按约定 29 判 A/B/C/保留待核 |

详情页无菜单但仍有路由 → 不能判 B；动态 import/自动注册尚未查清 → 保留待核；仍在用且明确重构 → C；仅在全部删除证据充分且明确重做时 → B。

**3. 决策门**（按 3 类处置规则）：

| 情形 | 默认行为 | 是否弹 AskUserQuestion |
|------|---------|----------------------|
| **A 仍在用 + 增量增强** | 按约定 28 复用，正常往下写 | 否 |
| **B 删除证据充分 + 明确重做** | `vcs_mode=git` 用 `git rm`；`vcs_mode=none` 逐项 `Path.unlink()` 删除证据清单内的文件。连带文件逐项证明独占，未证明的不删；数据库按下方 Step 4 单独核验 | 否 |
| **C 仍在用 + 需求重构（优先于 B）** | 弹 `AskUserQuestion`：「① 并存切流量（推荐）/ ② 直接替换 / ③ 单写新版保留旧版」三选一 | **是** |
| **保留待核** | 保留未知文件及关联资源，记录未核项；继续不依赖删除的工作，无法推进时返回有原因的失败信号 | 无人值守不询问、不自动删除 |

★ **删除执行门**：只有已填齐扫描记录且通过约定 29 证据门的 B 文件，才在 Phase 0A.5 内删除并复核结果。证据不足不能为了完成本步骤而扩大删除范围；删除失败不得声称已经清理。

★ **情形 C 的 `--unattended` 降级（无人值守不挂死）**：`/loop` 无人值守（带 `--unattended`）下情形 C **不弹 `AskUserQuestion`**——优先消费 PRD `autopilot_decisions` 死代码处置预声明；无预声明则取**保守默认「① 并存切流量」**（新版并存 → 切流量 → 旧版留待人工删除，最不破坏现网），并在终端 + autopilot #4 里程碑通知 WARN「死代码情形 C 走无人值守默认①，旧版删除待人工复核」，**绝不挂起等待**。仅交互式（无 `--unattended`）才弹三选一。

**4. 表数据安全检查**（情形 B 涉及后端 Entity / Mapper 删除时必跑）：

读取 `memory/databaseBaseline.md`、本版建表/应用台账及目标环境的只读元数据，核实表归属、消费者与数据状态。**基线未登记不等于表不存在或无生产数据**；取不到实际证据时保留表及关联资源、登记待核，不能生成或执行 DROP。

有存量数据/存活消费者时按 C 的兼容策略处理。即使已证实表无存量数据，删除或回滚 SQL 也须有本版部署/回滚授权与明确适用条件，不能因删除 Entity/Mapper 自动补 DROP。交互式缺失关键依据时集中询问；`--unattended`／`--from-batch` 按调用方待裁决或失败协议返回，不挂起、不猜空库。

**5. 留档**：
- 扫描清单：`memory/{version}/{user}/sprints/sprint-{NNN}-deadcode-scan-*.md`
- 删除清单：追加到 `docs/design/detail/{version}/*事实清单.md`「死代码删除清单」段
- Sprint 归档：完成后由 `/sprint-close` 把删除清单汇总到 `sprint-{NNN}.md`「死代码清理」段
- **不写 ADR**（按约定 29 — 删除死代码是清理工作非架构决策）

**6. 跳过条件**：
- 全部扫描结果归类为 A（无死代码） → 终端打印「✅ 无死代码识别，跳过 Phase 0A.5 删除动作」直接进入开发执行步骤
- `--skip-deadcode-scan` 旗标（仅用于已知本 Sprint 全是绿地新建的场景；不推荐常态使用）

**7. 与 Step X.0.0 上游级联同步的协作**：
- Phase 0A.5 的"删除旧文件"事件不属于"上游文档变更"，**不触发** Step X.0.0 上游级联
- 但删除清单必须写入 `*事实清单.md` 让下一个 Sprint 的 Phase 0A 能读到"该模块已重做"基线信息

> 分支 A 的 Phase 0A* 跑完后直接跳到下方「## Phase 序列（分支 A / B 共用）」，不进入分支 B。

---

## 分支 B：formal 累进新建 Sprint（仅 formal 父编排）

### Phase 0B.00：★ 约定 9 前置门（⛔ 最先跑，先于版本落点门与任何取号动作）

> 存在**未关闭 Sprint** 时**立即停下**要求先 `/sprint-close`，⛔ 不得继续。
> **不能等到 Phase 0B.2 的 `/sprint-start` 才拦**——那时 Sprint 号已被 `check_sprint_numbering.py next` 消耗、
> 六类 `NN_*.md` 增量已落盘；close 后重跑会拿到**又一个**新号，
> 上一轮产物成为无 Sprint 归属的孤儿。而独立分步执行时这些副作用根本不会发生。
> 判据与话术同 `/sprint-full` Phase 0B.0 前自检（那条已落地，本条照它办）。

```bash
python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version {version} --scope started --json
OPEN_RC=$?        # 0=无已启动未关闭轮次→继续；1=有→立即停下、先 /sprint-close；2=状态读错→停止并修复输入
```

> **判据单一信源 = `check_open_sprints.py`**（开工门检查跨用户的已启动记录与显式当前状态，扣除同时具备同行 ✅ 与 `sprints/sprint-NNN.md` 归档文件的关闭记录；**尚未开工的计划不阻断启动**）。
> ⛔ 不自行裁量、不记告警后继续 —— 本门漏判的方向是**放行**，而放行的代价是上面那段写的孤儿产物。

### Phase 0B.0：★ 版本落点决策门（单一信源 —— 累进前置，最先跑，先于任何持久副作用）

> **要解决的问题**：一个版本**已发布**（已归档、已打 tag、已建版本分支、已推送）之后、用户**尚未主动开始新版本规划**时，又提出新需求 / bug 修复。此刻执行体**绝不能自行裁量版本号**（如"向后兼容 → 就 patch"）**更不能静默创建新版本目录骨架、也不能静默往已发布版本累进**——版本号对外是 **SemVer 兼容性承诺 + 发布节奏**（产品/运维决策，非技术判断），re-release 还会**移动已推送的 tag**（有实际风险）。必须让用户**先选落点**。
>
> ⚠️ **本门是结构化决策门、不受「⛔ 统一决策纪律」的"禁自发反问"约束**——它满足该纪律「必须设门的正向判据」全部三条（会建持久目录 / 会产生对外承诺〔版本号·tag·分支〕/ 不可逆或回退成本高〔已推送 tag·分支〕，见本命令「⛔ 统一决策纪律」段正向判据）。**绝不能以"不许自发问"为由省掉本门**（下游越权正是这条纪律被误读为"一律别问"所致）。

**① 检测「当前版本已发布 且 未开始新版本规划」**（命令端 Bash，`{V}` = `AGENTS.md`「当前状态.当前版本」）：
```bash
V={version}                 # 形如 V0.2.0
VNUM=${V#V}                 # 去 V 前缀 → 0.2.0
VCS_MODE="${VCS_MODE:-$(python3 {{AIDP_HOME}}/scripts/vcs.py mode)}"
if [ "$VCS_MODE" = "git" ]; then
# 已发布信号（任一命中即已发布）：① 该版本存在 release tag（三风格全覆盖，与 version.md「tag 风格识别约定」同口径）
# ⛔ 必须区分「判定失败」与「判定为未发布」：两者都产出空值时，浅克隆 / 未 fetch --tags /
#    CI 无 tag 检出 / git user.name 与 memory 目录名不一致 / progress.md 格式不符 —— 任一情形
#    都会静默判"未发布"并累进，即把"版本未发布"当默认假设、不实际判定。
TAG_OK=1; git rev-parse --git-dir >/dev/null 2>&1 || TAG_OK=0
git fetch --tags --quiet 2>/dev/null || true          # 拿不到远端 tag 不致命，但要试一次
# ★ tag 识别**不自己拼 glob**，一律问 `release_scope.py` —— 它是三种风格（`V*` / `release-V*` / `v*`，
#   权威清单见 `flows/version/release-1.md`「tag 风格识别约定」）的单一信源。
#   ⛔ 别在这里自己拼 glob：与脚本各写一遍同一判据，任一处漏一种风格，
#   这道门就会把**已发布**版本判成未发布并往里累进（G-BUGFIX-1 禁止的事）。
TAGS=$(python3 {{AIDP_HOME}}/scripts/release_scope.py --version "$V" --json 2>/dev/null \
       | python3 -c 'import json,sys;d=json.load(sys.stdin);print("\n".join(t for t in (d.get("released_tags") or []) if __import__("re").sub(r"^(release-)?[Vv]","",t).split("-")[0]==sys.argv[1]))' "$VNUM" 2>/dev/null) || TAG_OK=0
RELEASED=$(printf '%s\n' "$TAGS" | head -1)
# ③ 第三信号（不依赖 tag 与文件名约定）：baseline 的 internal_released_at + 随 tag 冻结的部署基线
[ -z "$RELEASED" ] && [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" get internal_released_at --default "" 2>/dev/null)" ] && RELEASED="internal_released_at"
[ -z "$RELEASED" ] && [ -d "docs/deployment/$V/配置文件/全量" ] && RELEASED="deployment-baseline"
# ② progress.md「版本历史」/ 版本更新日志 标本版「✅ 已发布」
# ⛔ 版本号须转义 `.` 并要求版本边界（`V0.2.1` 不得命中 `V0.2.10 ✅ 已发布`）
V_ESC=${V//./\\.}; V_PAT="${V_ESC}([^0-9.]|$)"
[ -z "$RELEASED" ] && grep -qsE "${V_PAT}.*✅ ?已发布|已发布.*${V_PAT}" "memory/$V/$(python3 {{AIDP_HOME}}/scripts/vcs.py user)/progress.md" 版本更新日志.md 2>/dev/null && RELEASED="$V(状态已发布)"
# ⛔ fail-closed：tag 判定本身失败且其余信号均未命中 → 落点未知，按「已发布」进下方决策门，⛔ 不并入"未发布"
[ "$TAG_OK" = 0 ] && [ -z "$RELEASED" ] && RELEASED="unknown(tag-query-failed)"
elif [ "$VCS_MODE" = "none" ]; then
  # 无 Git 仅使用版本级本地记录；缺少明确证据不能由“无 tag”推导未发布。
  RELEASED=""
  [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" get internal_released_at --default "" 2>/dev/null)" ] && RELEASED="internal_released_at"
  [ -z "$RELEASED" ] && [ -d "docs/deployment/$V/配置文件/全量" ] && RELEASED="deployment-baseline"
  UNRELEASED=0
  V_ESC=${V//./\\.}; V_PAT="${V_ESC}([^0-9.]|$)"
  for progress in "memory/$V"/*/progress.md 版本更新日志.md; do
    [ -f "$progress" ] || continue
    if grep -qsE "${V_PAT}.*✅ ?已发布|已发布.*${V_PAT}" "$progress"; then
      [ -z "$RELEASED" ] && RELEASED="$V(状态已发布)"
    fi
    # 只有版本号同一行明确写未发布，且不存在任何已发布信号，才允许累进。
    grep -qsE "${V_PAT}.*未发布|未发布.*${V_PAT}" "$progress" && UNRELEASED=1
  done
  if [ "$UNRELEASED" = 1 ] && [ -n "$RELEASED" ]; then
    RELEASED="unknown(local-release-state-conflict)"
  elif [ "$UNRELEASED" = 0 ] && [ -z "$RELEASED" ]; then
    RELEASED="unknown(local-release-state-unverified)"
  fi
else
  RELEASED="unknown(vcs-mode-unrecognized)"
fi
echo "RELEASED=${RELEASED}"
```
> ⛔ **`TAG_OK=0`（Git tag 查询失败）或 `vcs_mode=none` 且无明确本地发布证据 → fail-closed**：将 `RELEASED` 置为 `unknown(...)`，交互式要求用户先核实并选定落点；`--unattended` 记录 `release-state-unknown` 待裁决并结束本次累进，不得自行创建 patch 版本或把无 Git 当未发布。即使本地证据命中，也仅表示需要版本落点决策，不表示已完成正式 Git 发布。
>
> 说明：Git 模式下若用户已开始新版本规划，「当前版本」已推进到未发布的新号，tag 查询成功且无已发布信号时 `RELEASED` 为空、本门自动不触发；无 Git 模式须有版本号对应的明确「未发布」本地记录且无已发布信号，才能让 `RELEASED` 为空；记录缺失或互相矛盾时需先核实发布状态。

**② ★ 决策前置铁律（不可逆序）**：`RELEASED` 非空时，**在用户选定落点并确认之前，绝不创建任何 `{新版本}` 持久副作用**——不 `mkdir docs/requirements/{新版本}/` / `docs/design/detail/{新版本}/` / `memory/{新版本}/`、不写项目记忆文件「当前状态」、不建 tag/分支。**决策 → 用户确认 → 才建目录**（事前一问，成本远低于事后 `git mv` 一批目录 + 回改状态文件）。

**③ `RELEASED` 非空 → 决策门（`RELEASED` 为空 → 跳过本门，直接进 Phase 0B.1 正常累进）**：
- **`RELEASED=unknown(...)`** → 发布状态不可核实，停止本次累进并保留原版本号；交互式请用户核实本地发布记录并明确落点，`--unattended` 记待裁决 `release-state-unknown` 并交上层失败处置，不使用下方已确认发布版本的默认 patch 路径。
- **交互式**（非 `--unattended`）→ `AskUserQuestion` **三选一**（命令端给推荐项 + 逐项讲清代价，**版本号语义 patch/minor 由用户定、执行体不自裁**）：
  - **① 落回已发布版本 `{V}`（re-release）**：增量并入 `{V}`、完成后走 `/version {V}` 情况 C 重新发布。⚠️ **风险必须明示**：re-release 会**强制移动已推送的 tag `v{VNUM}` + 强制重建版本分支 + 强制推送**；**若该 tag 已被他人拉取 / 已被 CI / 制品库消费，强制移动有实际风险**。适合：极小热修且确认 tag 未被下游消费。
  - **② 新开 patch 版本 `{x.y.z+1}`（推荐默认，风险最低）**：向后兼容的修补 / 行为补齐 → 新建版本目录 → 累进开发；**不动已发布的 tag**。
  - **③ 新开 minor 版本 `{x.y+1.0}`**：有功能语义的增量 → 新建版本目录 → 累进开发；不动已发布 tag。
  > patch vs minor 命令端可给**推荐 + 理由**（如"纯 bug 修复建议 patch、含新行为建议 minor"），但**最终由用户确认**——版本号是对外兼容性承诺，不由执行体技术判据决定。选 ①→转 `/version {V}` 情况 C；选 ②/③→以用户确认的新号继续 Phase 0B.1。
- **`--unattended`**（罕见命中——autopilot 版本发现只挑未发布的 S0/S1 版本作开发目标、通常不会把已发布版本当累进目标）→ **不弹窗**，按**保守默认 = 新开 patch 版本 `{x.y.z+1}`**（**不动已发布的 tag、风险最低**，绝不默认 re-release 去移动已推送 tag）继续，并在报告 + 终端 + baseline **`versions.{V}.builds[current_build].decidable_skips[]`**（无 `current_build` 时才回落版本级 `versions.{V}.decidable_skips[]`）（`post-release-accrue-defaulted-patch`）**留痕**：「已发布版本 {V} 收到新累进请求 → 无人值守按保守默认新开 patch {x.y.z+1}；如需落回 {V} re-release 或改 minor 请人工处置」。**绝不静默当常规累进、绝不自动 re-release 动 tag**。

### Phase 0B.1：累进 Sprint 序号

```bash
# ★ 取号一律走脚本，【绝不】自己 glob 当前版本目录（见下方 Why）
NEXT=$(python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next)   # 形如 004
```

> ⛔ **Sprint 编号是【项目全局流水号】，跨版本连续自增、不随版本重置**（`06_版本与用户目录约定.md` §3.3）。
> ⛔ 扫描路径**不得带 `{version}` 限定**（带了就等于每个新版本从 `sprint-001` 重新开始）。
> 成因见 `{{AIDP_HOME}}/flows/sprint-dev/rationale.md`「Sprint 编号为何必须跨版本扫」。于是同一项目里存在多个
> `sprint-001`，bugfix 记录、`docs/testing/{version}/sprint-{NNN}/`、Sprint 归档
> 全部产生歧义。脚本的 `next` 子命令**跨全部版本**扫描取 MAX+1，回检见 `check` 子命令。

取得原流程真实 Sprint 号后，在任何 start/子命令派发前绑定或派生 formal 上下文。版本/批次父身份不绑定单个 Sprint；单 Sprint 的 full 无号上下文才 bind。绑定/派生不是开工批准，后续契约与 start 门照旧。`NEXT` 必须是上方原取号结果，工具调用不共享 shell 时显式重绑该结果，禁止再取一次号。

```bash
CONTEXT_ENTRY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["entry"])' "$EXECUTION_CONTEXT") || exit $?
case "$CONTEXT_ENTRY" in
  sprint-autopilot|sprint-batch|version) CONTEXT_OPERATION=fork ;;
  *) CONTEXT_OPERATION=bind-sprint ;;
esac
SPRINT_POLICY_ARGS=()
if [ "$CONTEXT_OPERATION" = fork ]; then
  SPRINT_ALLOW=$(python3 - "$EXECUTION_CONTEXT" <<'ACTIONS'
import json, sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from execution_policy import BASE_ACTIONS, COMMAND_ACTIONS
parent = json.load(open(sys.argv[1]))
development = BASE_ACTIONS | set(COMMAND_ACTIONS["sprint-full"])
print(*["--allow-action=" + a for a in sorted(development & set(parent["allowed_actions"]))])
ACTIONS
  ) || exit $?
  [ -n "$SPRINT_ALLOW" ] || { printf '%s\n' 'NOT_REQUESTED: 无Sprint开发动作'; exit 0; }
  read -ra SPRINT_POLICY_ARGS <<< "$SPRINT_ALLOW"
fi
SPRINT_CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py "$CONTEXT_OPERATION" --root . \
  --execution-context "$EXECUTION_CONTEXT" --sprint "${NEXT:?原流程已分配的Sprint号缺失}" "${SPRINT_POLICY_ARGS[@]}" --json) || exit $?
EXECUTION_CONTEXT=$(printf '%s' "$SPRINT_CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
```

完成回传包含真实 Sprint 号与当前子 `execution_context`；外层 bugfix/full 后续 test/close 消费该子路径。autopilot 的版本节点仍保留父路径，不用此子路径覆盖。重试已有子任务直接继承它，不能重新从版本父启动累进取号。

### Phase 0B.1.1：★ 自动文档增量流

**触发条件**：分支 B 必跑契约放行；以下正式成文配方仅 document 已授权时执行，未授权记 NOT_REQUESTED、保留最小规格与事实登记；`skip-doc-sync` 只影响成文调度，不能跳过规格、反转清算、台账或 M/L 完成门。

**第一动作 = Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`**，按“契约卡放行”先判档、写卡与四族义务，再分流。该片是分档时机与并行汇合的唯一权威；下方步骤 1–6 是**正式成文配方**，不能对所有档位无条件串行执行。
- **S**：先契约卡＋受影响四族短行，跳过下方完整成文配方进入 Phase 0B.1.3/0B.2；用例按本节配方步骤 4 判定并双重登记，required=true 时正式用例必须生成，不能把卡的 AC 当用例。后续完整成文由约定 22 收口或显式 `--cascade-now` 负责。
- **M**：契约卡放行后启动 Sprint，Phase 1 同时派代码与 docs；docs 按下面配方依次成文，**完整文档硬门移到本轮汇合、先于 `/sprint-test`**。主流程记录 docs owner/任务/写集，不能把文档义务交给无人负责的末尾兜底。
- **L**：下面配方与完整文档硬门均在开发前完成，再进入 Phase 1。
- **Step X.0.0**：检测实现期新增漂移、复核实际档位、主流程登记工作单；不重新生成 docs 已完成的同一批内容。正式补充与台账合并仍各走 `--supplement` / `--ledger-cascade`，不能混用落点。

**典型场景**：产品口述新功能 → 研发用 `/sprint-dev "<描述>"` 直接开发 → 历史问题是只追代码不追文档 → 现在用本流程自动追平。

**正式成文配方**（L 开发前、M docs 分支、S 收口时执行；docs 内按依赖串行，代码可按契约并行。任一步失败记缺项，交原 docs Agent 修正；确需产品决策才待裁决，不静默放行）：

1. **记录口述补充**：由主流程把命令参数 `"<描述>"` + 当前时间 + developer_identity 写入来源文件；契约放行时已经创建则复用同一文件，docs 不重复创建：
   `docs/requirements/{version}/产品提供/口述补充-{YYYYMMDD-HHMM}.md`（每次累进一份；用时间戳区分多次口述；该目录已有 PRD 时本文件作为同级补充）

2. **生成研发需求补充**：经 `/sprint-requirements {version} --supplement={NN} [--unattended]` 编排（研发需求唯一入口，内部调 `ux-logic-extractor` skill 增量补充、prompt 驱动；★ **不直调 SKILL**——直调会跳过命令端的落盘归一 / 多系统拆分 / 头部元数据表 / AIDP 硬规范回检，与同轮其余三层 `/sprint-design --supplement [--unattended]` · `/sprint-plan --supplement [--unattended]` · `/sprint-selftest --supplement [--unattended]` 走命令中介保持一致），输入：
   - 口述补充文件（步骤 1 产出）
   - 当前 `docs/requirements/{version}/研发需求/01_研发需求.md`（既存基线；历史裸 `00_研发需求.md` 兼容）
   - 当前 `docs/prototype/{version}/code/` + `mockup/`（如有，作为交互细节参考）

   输出研发需求增量文档（NN 按目录现有序号累进），并在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间）。

   > ★ **增量文档命名（按约定 15）**：所有增量文档统一 `NN_<业务主题>.md`（NN 续编目录现存最大序号 +1，排除 `00_索引`/`98_`/`99_`）——**文件名不带"补充"字眼**；补充身份只记入 `00_索引.md`（类型=补充 + 更晚生成时间）。上游 SKILL 本就产出干净 `NN_<业务名>.md`（已禁"补充/追加"语义前缀，各 SKILL 的 `check_doc_split.py` 亦禁），命令端**只做序号续编校正、绝不回补"补充"字眼** + 维护 `00_索引.md`（脚本见 `{{AIDP_HOME}}/flows/version/planning-4.md`（`version.md` Step 2.4.4 现仅是一行指针））。下文括注（如"研发需求增量"）仅标识增量内容所属文档类型。

   skill 内置的不中断原则、数据闭环完整性等会自动生效（沿用主文档 `Q-NNN` 编号空间往后递增，数据闭环孤立端用 `Q-FLOW-NNN`），命令端按 AGENTS.md 约定 21 不复述具体条款，详见 `{{AIDP_HOME}}/skills/ux-logic-extractor/SKILL.md`。

2.5. **★ 口述规模档位判定门（`sup_scale`）——开发前已生产，此处复核并传递**

   判据与字段的单一信源 = `flows/sprint-dev/incremental-contract.md`“契约卡放行”。**判档发生在步骤 1/2 成文之前**，不能先跑完整需求 SKILL 再决定是否需要它。复用 `versions.{V}.sprints.{新NNN}.dev_scale`，并保留 `versions.{V}.sprints.{新NNN}.sup_scale` 的 REQ/PAGE/第三方等原字段，两者 tier 相同；正式需求揭示了新表/破坏性变化时立即升 L、重过开发前门。

   **S（语义子档）**的「受影响结论清单」仍逐条包含落点、file:line、旧结论、新结论、失效/改写/不受影响；写入契约卡，正式需求成文时回链。空表或整体描述不算完成，约定 34 安全性回答不可省。

   以下正式调用仍显式传 `--scale={档位}`，只写 baseline 不传参视为未执行档位策略。M 设计合册另带 `--compact-contract=<契约卡路径>`，命令端记录版式映射，不能谎称上游 scale=M 原生输出一册。

3. **触发增量设计**：调 `/sprint-design {version} --supplement={NN} --scale={档位} [--unattended]` 派生增量设计；M 另带 `--compact-contract=<契约卡路径>`，设计/接口默认合册、保留上游强制独立专题：
   - Step 0.6.4.7 全扫 code/ 拿当前代码现状（含本 sprint 即将新增功能可能已部分实现的情形）
   - Step 0.3 按四象限对比口述新功能 vs 代码现状：判定走"② 新增"还是"③ 代码超前-补写"
   - 以增量 prompt 驱动调 dev-logic-architect（按其 SKILL 增量约定，无 mode 参数）产出详细设计 / 接口设计 / 数据库设计的补充文档（均归一为 `NN_<业务主题>.md`，按实际范围）
   - **★ 路径占位符显式传参**：调 dev-logic-architect 补充时，必须显式传 `docs/init/06_版本与用户目录约定.md` §2.5.7 映射表的 5 个占位符值，禁止 SKILL 自动推断

3bis. **★ 触发增量研发执行计划（独立一步，不能并进步骤 3）**：调 `/sprint-plan {version} --supplement={NN} --scale={档位} [--unattended]` 产出 `docs/plans/{version}/NN_<业务主题>.md`。
   > ⛔ **`/sprint-design` 不产研发执行计划**——它全文不涉及 `dev-execution-planner`，其补充模式产物只有 详细设计 / 接口设计 / 对外开放接口 / 数据库设计 / DDL SQL 五类。⛔ 因此**不得把"计划增量"并进步骤 3**——那会让下方硬门第 6 项（**不可 N/A 的必 Pass 项**）无人生产、恒 Fail。成因见 `{{AIDP_HOME}}/flows/sprint-dev/rationale.md`「计划增量为何必须独立一步」。
   > 即便临场改为直调 `dev-execution-planner` 兜住，也会绕过 `/sprint-plan` 的 Step 1.5 三脚本回检、Step 1.6 SQL 路径回写、Step 2 关联文档注入——故必须走命令编排、不得直调 SKILL。

4. **★ 研发自测用例适用性（先判后生成）**：主流程执行 `check_case_ledger_pending.py --prepare` 读取真实外层意图，将读数交 docs；`required=true` 才生成正式用例，`false` 则双重登记欠账后跳到步骤 5。S 同样执行本判定，不能因为跳过成文配方而漏掉它。确需正式用例而缺增量计划时先通过既有生成链补齐必要上游输入，不能给 SKILL 假计划或拿卡的 AC 充正式用例。纯技术内部调整也必须留痕，不能只打印 WARN。

   | 外层意图 | prepare 参数 | 行为 |
   |---|---|---|
   | autopilot 安排后续实测 | `--context autopilot` | 本轮生成 |
   | sprint-batch 未跳过 Step 6 | `--context batch` | 本轮生成 |
   | direct 只开发，或 batch 已跳过实测 | `--context direct`；或 `--context batch --skip-aiauto-test` | 双重登记延期 |
   | 用户显式要求实测，或父链传 `--aiauto-test-required` | 对应 context 加 `--require` | 必须生成（优先于子批次局部 skip） |

   ```bash
   python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version "{version}" --sprint "{新NNN}" \
     --prepare --context "{direct|batch|autopilot}" --reason "{本轮实际实测安排}" --json
   # 按上表附加 --require 或 --skip-aiauto-test；非零退出先修状态，不继续。
   ```

   下列生成动作仅在 `required=true` 时执行：经 `/sprint-selftest {version} --supplement={NN} --scale={档位} [--unattended]` 编排（研发自测唯一入口，内部调 `dev-manual-testcase` skill 增量补充，prompt 驱动），输入：
   - `NN_<业务主题>.md`（研发需求增量，步骤 2 产出，本次新增 / 修订的功能点）
   - `NN_<业务主题>.md`（详细设计 / 接口设计 / 研发执行计划增量，步骤 3 产出，与功能点关联的接口/页面/任务）
   - 原研发自测用例（`研发自测/02_自测用例-总览.md`（多文件）或 `研发自测/02_全量自测用例.md`（单文件）；研发自测方案 `研发自测/01_研发自测方案.md`；旧锚布局兜底 `研发自测/01_自测用例-总览.md`·`研发自测/00_研发自测方案.md`·`研发自测/00_研发自测.md`；基线，只读）
   - `code/` 已有代码
   - **★ 路径占位符显式传参**：必须显式传 `{测试文档目录}=docs/testing/`（覆盖 SKILL 默认 `docs/test/`；映射表见 `docs/init/06` §2.5.7）

   skill 工作要求：仅针对本轮新增/修订的功能点输出新用例或修订用例，未变功能不重复；原型变更必须重新对齐"操作对象 + 预期现象"。skill 内置的数据一致性与溯源原则 + 上游引用规则会自动生效，命令端按 AGENTS.md 约定 21 不复述，详见 `{{AIDP_HOME}}/skills/dev-manual-testcase/SKILL.md`。

   输出 `docs/testing/{version}/研发自测/<NN>_<业务主题>.md`（按 AGENTS.md 约定 15 统一数字前缀规则：NN = 目录现存最大序号 + 1、用例从 `02_` 起，文件名不带"补充"字眼；★ **一律在 `研发自测/` 同目录平铺续编、严禁再拆二级子目录**——SKILL「文件命名总则」要求同目录 `NN_` 前缀平铺，其硬门 `check_testcase_format.py` 只 `glob("*.md")` 非递归，落进子目录的用例会整体逃检），并在**研发自测专职索引** `00_索引.md`（及 `01_研发自测方案.md` 的「用例索引」段 / `02_自测用例-总览.md`）追加登记该增量（研发自测目录已对齐通用范式、导航锚 = `00_索引.md`，见约定 15）。新增用例 ID 全局唯一（继承原主文档编号空间，往后递增）。

   **延期终态**：`--prepare` 返回 `required=false` 即已把状态写入 baseline 和用例族增量册；不用额外重复 `--defer`。后续 `/sprint-aiauto-test` 必须先生成这些用例，不允许沿用该 false 跳过显式测试请求。

**步骤 4 完成后硬收口**：若本轮 `aiauto_test_required=true`，正式用例文件已经生成且用例族增量已由 `--ledger-cascade` 收口，必须执行：

```bash
python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version "{version}" \
  --sprint "{新NNN}" --complete --reason "正式研发自测用例已生成并通过用例族级联前置门" || exit 1
```

5. **更新各目录导航锚**：本轮新增的 6 类增量文档在对应目录导航锚各追加一行（类型=补充 + 生成时间）——研发需求 / 详细设计 / 接口设计 / 数据库设计 / 研发执行计划 / **研发自测用例**均 → `00_索引.md`（研发自测已对齐通用范式，另在 `01_研发自测方案.md` §8 用例索引段同步登记业务导航）

6. **完成回传**：列明已生成的需求/设计/计划与当前契约修订；用例真实二选一写「正式用例已生成并通过回检」或「延期并已双重登记，待实测前补齐」。M docs 回主流程汇合，L 回开发前放行，S 收口回成文结果；不得重复启动 Sprint、不得在延期状态宣称已生成用例。

**★ Phase 0B.1.1 正式文档硬门（L 开发前 / M 汇合时 / S 显式成文时）**：

> 契约放行由 `incremental-contract.md` 负责；下表核正式产物，**不把 S/M 的开发前契约门替换成六册存在性门**。L 未通过不得开发；M 未通过不得进入 `/sprint-test` 或宣称本轮交付完成；S 默认只契约＋台账，不虚报正式文档/用例已经生成。成文失败交原 docs Agent 补齐，不自由反问“要不要补”。

| # | 校验项 | Pass 判据 | Fail 处置 |
|---|--------|-----------|-----------|
| 1 | 口述补充落盘 | `docs/requirements/{version}/产品提供/口述补充-*.md` 存在且非空 | 补写步骤 1 |
| 2 | 研发需求补充 | `docs/requirements/{version}/研发需求/NN_*.md`（本轮 NN）已生成 | 回步骤 2 重跑 `ux-logic-extractor` |
| 3 | 详细设计补充 | `docs/design/detail/{version}/NN_*.md`（详细设计）已生成 | 回步骤 3 重跑 `/sprint-design --supplement [--unattended]` |
| 4 | 接口设计补充 | 本轮涉及接口 → 接口设计增量已生成；不涉接口 → 标 N/A | 涉接口却缺 → 回步骤 3 |
| 5 | 数据库设计补充 | 本轮涉及表/字段 → 数据库设计增量已生成；不涉库 → 标 N/A | 涉库却缺 → 回步骤 3 |
| 6 | 研发执行计划补充 | `docs/plans/{version}/NN_*.md`（研发执行计划增量）已生成 | 回**步骤 3bis** 重跑 `/sprint-plan --supplement [--unattended]`（⛔ 不是步骤 3，`/sprint-design` 不产计划） |
| 7 | 研发自测用例补充 | `docs/testing/{version}/研发自测/NN_*.md` 已生成；或 `--prepare` 明确延期、baseline 与用例增量册双重留痕（含纯技术内部调整） | required=true 却缺用例，或延期未留痕 → 回步骤 4 |
| 8 | 各目录 `00_索引.md` 登记 | 上述已生成的增量在对应目录 `00_索引.md` 均有"类型=补充 + 生成时间"登记行 | 缺登记 → 回步骤 5 补登记 |

- **N/A 合法**：项 4/5 在本轮确无对应变更时、项 7 在步骤 4 明确延期且双重留痕时标 N/A（附一句判据，如"本轮无接口变更"）即算 Pass；项 1/2/3/6/8 为**必 Pass 项**，不可 N/A。
- **M 合册同样算 Pass**：项 3/4/5 按实际合册中的详细设计/接口/数据库章节及契约回链核对，不要求三个独立文件；适用内容缺失仍 Fail。上游强制独立专题照旧。
- **S 契约放行不等于正式成文通过**：契约卡＋台账缺一即 Fail；语义子档的「受影响结论清单」须逐条有处置。正式成文时按 `--supplement` 新增或 `--ledger-cascade` 合入既有册并刷新索引，不能虚报。
- **`skip-doc-sync` 不豁免 M/L 完成硬门**：已延期的义务保留可发现状态，不能仅凭 WARN 返回成功。
- **无人值守（`--unattended`）同样受硬门约束**：Fail 项按上表"Fail 处置"自动重跑对应 SKILL；重跑仍 Fail → 转失败处置（熔断冻结 + #4 里程碑通知 WARN），**不挂起、也不放行带病开发**。

**显式延期**：`skip-doc-sync` 下仍须记录口述、完成契约卡与反转门，主流程原子取号后把本轮口述变更写进受影响各族台账（见 `{{AIDP_HOME}}/reference/开发期族增量.md`）。S 可以带已登记成文义务继续；M 必须在汇合时补齐、L 必须开发前补齐，不能用该参数宣告缺件通过。台账与工作单是后续可发现的输入，终端 WARN 不能替代落盘。

> 编号说明：Phase 0B.1.2 为退役编号、不使用（保留以免改动他处对 0B.1.3 的直引）。

### Phase 0B.1.3：★ 开发期口述追加 / 口径反转的处理（约定 34 ⑥ 决策门）

> ★ **单一信源，`/sprint-full` 模式 B Phase 0B.3 同用**（它只做编排触发、不复述本处判定）。

> **本门可在分支 B 的任意时点触发，包括 Phase 0B.1.1 已跑完、开发已经开始之后**——产品在同一轮里追加第 N+1 条口述、并且**反转**了上午刚写进文档的结论，是真实高频场景（下游实证）。原流程假定「口述 → 一次性写四层文档 → 开发」是线性的，**没有描述"文档已写完、开发已开始，此时口述追加或反转"该怎么办**，执行体只能自行决定"重跑 0B.1.1（重复生成）还是就地订正（不知道哪些段落失效）"。本门补上这段。

**触发**：Phase 0B.1.1 完成后（含开发进行中），用户 / 产品又给出新的口述内容。

1. **先判「追加」还是「反转」（不判定就动手 = 本门最常见的失效）**

   | 判定 | 判据 | 处置 |
   |---|---|---|
   | **追加** | 新口述**只增加新结论**，不与任何已写入文档的结论矛盾 | 主流程更新契约修订、复核档位、登记四族；S 保持攒批，M 更新 docs 任务，L 先补齐文档；受影响工作单重派 |
   | **反转** | 新口述**推翻了已写入文档的既有结论**——口径反向 / 白名单方向调转 / 默认值·状态机·权限范围改写 | **必走下面第 2~4 项，一步不省** |

2. **失效结论清算（逐条打勾，⛔ 不许靠"重跑一遍 0B.1.1"代替）**

   列出**所有引用旧结论的落点**，逐条判「失效 / 改写 / 不受影响」并留痕：

   | # | 落点类型 | 典型位置 |
   |---|---|---|
   | 1 | 研发需求条目 | `docs/requirements/{version}/研发需求/NN_*.md` 的规则条 |
   | 2 | 详细设计 ADR 的「代价与守卫」段 | `docs/design/detail/{version}/NN_*.md`（★ 旧结论常写成「⛔ 不会误放行 X」这类**断言**，反转后当场失效）|
   | 3 | 自测用例的断言方向 | `docs/testing/{version}/研发自测/NN_*.md` 的 `TC-*` 预期现象 |
   | 4 | 反向断言式子 | 同上（`Z-*` 零残留断言，方向反转后式子本身要改）|
   | 5 | 各处铁律 / 禁止性注释 | 代码注释里的「⛔ 别改回 X」——反转后这句话本身就是错的 |
   | 6 | 代码里的 `REQ-XXX` 编号注释 | `code/**`（旧编号会把后来者引回错误方向）|

   > ⛔ **重跑 Phase 0B.1.1 不是本步的替代品**：重跑只会**再生成一份新增量**，旧结论**仍原地留着并继续"生效"**。

3. **⭐ 强制回答一个问题（本门最不可省的一条）**

   > **「旧口径下被判定为安全 / 无害的设计，在新口径下是否仍然安全？」**

   **口径反转会在一行代码都不改的情况下改变安全等级。** 下游实证：某 resolver 的 fail-closed，旧口径下判据源失败只会把资源误标 ⇒ 后果是**展示错误**；口径反转后，同一处误标立刻变成「本该统一开通的资源上出现**可用的解绑按钮**」，而解绑在上游是永久取消、不留恢复快照 ⇒ **不可逆数据破坏**。详设里那句「⛔ 不会误放行解绑」若不重写，就成了误导后人的**错误结论**。

   **⛔ 这个问题不会被任何静态检查发现**——没有脚本能判"安全等级变了"。必须在本步显式回答并把结论写进详细设计的对应 ADR；答案为"不再安全"时，**当轮补齐守卫**（不得留到下个 Sprint）。

4. **用显式作废标记，不用静默改写**

   - 被推翻的条目：原地加 `⛔ 本条已于 sprint-{NNN} 反转，改见 REQ-XXX / ADR-XXX`，**保留原文**再写新结论。
   - 整册被推翻的：在该册头部加**整册作废标记**并指向新册。
   - ⛔ 直接把旧文字改掉 = 代码注释里引用的旧编号无处可查，后来者只能按旧印象改回去。

**完成判据**：第 1 项判定结论 + 第 2 项清算表 + 第 3 项的安全性回答，三者写进本轮契约卡（无卡的存量路径写口述补充或研发需求增量）；缺任一项不得继续开发。开发期当场只落≤10行的显式作废标记并登记需求族已知失准点，全文订正在成文/收口时完成。主流程递增 contract_revision，暂停受影响写集并重派；旧修订回传不得当成新契约完成。

### Phase 0B.2：启动新 Sprint

```
执行：/sprint-start {新NNN} --execution-context "$EXECUTION_CONTEXT" [--unattended]（无人值守时透传；调用上下文必须附契约卡路径、修订、dev_scale 与放行证据）
```

### 转入共用「Phase 1 开发执行」段（本命令核心）

分支 B 不另设开发步骤、也不另设串联步骤：跳到下方「## Phase 序列（分支 A / B 共用）」，从 `Phase 1 开发执行` 起逐项执行到 `Phase 2-4 自动串联后续`（**串联规则的单一信源 = 该段的 `### Phase 2-4`**，本分支不复述、不改判定）。

---

## Phase 序列（分支 A / B 共用；与上方 `Phase 0A*`/`Phase 0B.*` 同级，同属一条 Phase 序列）

> 本段按序含 4 节：**Phase 1 开发执行** → **★ 开发完成后：自动回写需求 + 设计文档** → **完成前验证** → **Phase 2-4 自动串联后续**。两个分支跑完各自的 `Phase 0A*`/`Phase 0B.*` 后都汇入此处、按序跑完 4 节。

### Phase 1：开发执行（两种分支共用 — 下设 Phase 1.0~1.4）

> ⚠️ 关键规则一句提醒：**Phase 1.2 后端开发 Step 1 必做「开发期 SQL 自动应用（幂等、检测驱动）」（约定 6）**、**Phase 1.1.5 首次写码前必过「`code/{side}/{子项目}/` 目录确认门」（约定 18 铁律）**——这两处漏做会复现「部署后表缺失」/「源码根直放 `code/frontend` 父目录」两类下游事故。
>
> ⛔⛔ **详细步骤已外置为 2 个分片、进入 Phase 1 开发的【第一动作】= 按需加载**：Phase 1.0–1.4 的完整步骤在 `{{AIDP_HOME}}/flows/sprint-dev/` 下 **2 个分片**，**进入本段第一动作 = 按序 Read 两片**、逐项执行：
> 1. **`{{AIDP_HOME}}/flows/sprint-dev/phase-1-dev-1.md`** — Phase 1.0pre / 1.0 / 1.1 / 1.1.5 / 1.2（后端开发）
> 2. **`{{AIDP_HOME}}/flows/sprint-dev/phase-1-dev-2.md`** — Phase 1.3（前端开发）/ 1.4（并行开发）
>
> 下方骨架仅供"知道有哪几步 + 定位"，**权威判定与操作一律以分片 flow 文件为准，绝不凭本骨架或记忆略过任一子步骤，也不得只读其中一片**。

**Phase 1 子步骤骨架（详见 `phase-1-dev-1.md` + `phase-1-dev-2.md`）**：

| 子步骤 | 作用（一句话） |
|---|---|
| **1.0pre** | ★ 开发前置（本命令 `--scale` 等派生值的置位点；后续判据依赖它，⛔ 漏跑即恒取默认）|
| **1.1** | 确定开发范围（前端/后端/全栈）|
| **1.1.5** | ★ 确认/创建 `code/{side}/{子项目}/` 目录（约定 18 铁律，首次写码前必过）|
| **1.2** | 后端开发（输入文件必读 + 开发步骤〔含 Step 1 开发期 SQL 自动应用〕+ 核心原则）|
| **1.3** | 前端开发（输入文件 + 开发步骤 + 视觉/内容/操作逻辑三层对齐）|
| **1.4** | 并行开发（★ 全栈场景推荐）|

> 收口：Phase 1.0–1.4 全部完成 → 进入下方「★ 开发完成后：自动回写需求 + 设计文档」段。**执行前务必已按序 Read `phase-1-dev-1.md` + `phase-1-dev-2.md` 并按其逐项完成，不能只看本表。**

---

### ★ 开发完成后：自动回写需求 + 设计文档（含研发需求回写）

> ⚠️ 关键规则一句提醒：**Step X.0.0 是约定 22「上游文档级联同步」的统一入口**——开发引入超出既存文档范围的实质变更（新增接口/表/业务规则/页面/功能点、原型字段被覆盖/裁剪、Mock→真实、语义·口径·范围变更）时必须按 4 级触发（研发需求→详细设计→研发执行计划→研发自测用例）自动级联，**禁止绕过它直接调单一 SKILL 补单层**；Step X.7/X.8 是约定 25 配置/部署变化的机器待同步登记，规划/正式发布再集中校准操作指引。

> ⛔⛔ **详细步骤已外置为 3 个分片、进入本回写段的【第一动作】= 按需加载**：Step X.0.0–X.8 的完整步骤在 `{{AIDP_HOME}}/flows/sprint-dev/` 下 **3 个分片**，**进入本段第一动作 = 按序 Read 三片**、逐项执行：
> 1. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-1.md`** — Step X.0.0（上游文档级联同步检测）
> 2. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-2.md`** — Step X.0 / X.2 / X.3 / X.4 / X.5 / X.6 / X.7
> 3. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-3.md`** — Step X.8（部署操作变化待同步）+ **累进路径的产物审计收口**
>
> 下方骨架仅供定位，**权威判定与触发条件一律以分片 flow 文件为准，绝不凭本骨架或记忆略过任一 Step，也不得只读其中一片**。

**触发条件（详见 flow 文件）**：开发引入 新增/改接口 · 新增表/改表结构/新增字段 · 新增公共组件/页面/模块 · 新增外部依赖 · 调整 context-path/端口/proxy/API 前缀（配置事实）· 开发期发现"需求漏项" 任一即触发回写。

**回写步骤骨架（详见 `postdev-writeback-1.md` + `-2.md` + `-3.md`）**：

| Step | 作用（一句话） |
|---|---|
| **X.0.0** | ★ 上游文档级联同步检测（约定 22 统一入口，4 级触发 + 默认攒批入台账；**仅破坏性变更弹确认门**——document 已授权才执行成文，未授权保持事实登记）|
| **X.0** | 研发需求回写（含开发期需求漏项）|
| **X.2** | 调 dev-logic-architect 更新设计（走 `/sprint-design --ledger-cascade [--unattended]` 编排；⛔ **不是 `--supplement={NN}`** —— 本段是约定 22 收口级联，就地改主文档、不新建分册，落点门会判 exit 1）|
| **X.3** | 调 `/sprint-plan --ledger-cascade [--unattended]` 更新研发执行计划（⛔ 同上，不是 `--supplement`）|
| **X.4** | 更新项目级 memory（架构级变更时）|
| **X.5** | 更新 SQL 脚本 |
| **X.6** | ★ 更新 *事实清单.md（配置事实变更时）|
| **X.7** | 配置操作变化登记（约定 25）|
| **X.8** | 部署操作变化待同步（约定 25，不在日常补 Markdown）|
| **X.8 收口** | ★ 累进路径的产物审计（docs-audit 已授权且新内容未被同 hash 证据覆盖 → 派 version-auditor）|

> 收口：回写段完成 → 进入下方「完成前验证」。**执行前务必已按序 Read `postdev-writeback-1.md` + `-2.md` + `-3.md` 并按其逐项完成，不能只看本表。**

---

### 完成前验证

调用 `superpowers:verification-before-completion`：
- 确认本 Sprint 范围内代码已实现、无遗留 TODO
- ★ **不在开发阶段逐任务编译/校验**——后端编译 / 前端校验（lint + 类型检查，**不打包**）已收敛到 **Sprint 验收（`/sprint-test`）**，届时**仅处理本 Sprint 改动的一侧**（改前端才校验前端、改后端才编后端）且以**资源受限方式**执行（`nice` + 限并发，避免 CPU 打满），配方见 `agents/backend.md`「Step 7」/ `agents/frontend.md`「Step 4」。前端验收期只做 lint + 类型检查、**不跑完整打包**，部署打包由使用者按需自行执行。静态证据用 entry_context static 生成；普通开发仍须自动完成 related-test，真实 skip 仅受限返回

更新 `memory/{version}/{user}/activeContext.md`：
- 在「子迭代记录」中追加开发阶段的 Round 记录
- 在「已完成工作」中追加完成项
- 更新「当前工作焦点」为"开发完成，等待测试"

> ★ **若本命令触发 `git commit`**：主流程汇合合法写集并集后按 `incremental-contract.md`“写集派发”先require_action(commit)，传 `--execution-context`、`--owner` 与重复 `--allow-path` 给 `commit_gate.py --quiet`，每次读取完整 JSON；暂存区外路径 WARN 核对归属，不覆盖他人索引。退出码3/4是欠账信号；5/NOT_AUTHORIZED硬禁止提交，不能按3/4继续；台账结构/清理异常修正复核，实际级联仅由阶段入口或显式 `--cascade-now` 触发，CICD 欠账按约定 31.5 补监听。默认仅主流程写 Git，用户明确授权 worker 时须串行交接索引。

> **日常累进的推送时机**：部署触发前只复用已授权验证的当前证据；仅 commit/push/deploy 不追加测试、重回归或审计。未授权测试记 NOT_REQUESTED，不变成部署欠账。

> ★ **推送分类与监听（约定 31.5，独立跑本命令时同样适用）**：本命令 push 前先调用 `python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --version "$VERSION" [--build "$BUILD"]` 并写入当前 build（⛔ 别写成 `classify_commit_change.py`：那个只出分类、无 `--version`/`--build`、不落盘）。无正式代码变更且分类无错误时，仍校验 push 成功并记录 `cicd_skipped=true`，不触发/监听远端 CICD、不跑就绪探针；正式代码变更或分类错误时，若项目已接入 CICD（`memory/aidp-config.yaml` 的 `cicd.provider` ≠ `none` 且 `cicd.pipelines` 已配，默认 GitHub Actions），则经 `python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode watch --commit <sha> --env <env>` 监听本次推送触发的运行至终态、仅获 deploy grant 且预算允许才主动 retry 和运行就绪探针；push 单独授权只读监听。★ 监听结束后必须 `python3 {{AIDP_HOME}}/scripts/classify_push.py --version "$VERSION" --record-terminal success|failed|unknown:<原因>` 记部署终态（约定 31.5；漏记 1 小时后 `commit_gate` 报 `pending_cicd`）。分类结果缺失、调用失败或无法落盘时按正式代码路径 fail-closed。规则单一信源 = 约定 31.5 +「推送分类与监听不变式」（`{{AIDP_HOME}}/flows/sprint-autopilot/invariants.md`）。

---

### Phase 2-4：自动串联后续（分支 A / B 共用 —— 串联规则单一信源）

**串联按父策略选择**：只有 related-test/review/full-cvl 获授权时才调用 `/sprint-test --execution-context "$EXECUTION_CONTEXT" [--unattended]`；原始参数与无人值守标记继续透传。test 子入口继承，不因入口名自行取得公开组合。实现修复需 implement；同根因同 inputs 未变化则停止 retry，报告事实与当前授权范围。

默认开发完成 static 后自动进入当前 task/单 Sprint 的 related-test，真实失败修复复验，再按 `light-context.md` 收口；无测试/缺工具不能当 PASS 或 NOT_REQUESTED。formal 需要关闭时进入 `/sprint-close {NNN} --execution-context "$EXECUTION_CONTEXT" [--unattended]`，只消费已要求的证据并执行原编号/归档门；不因 close 补跑测试或审计。父编排传 `skip-test` 只移交测试，不取消 related-test；仅用户真实明确 skip 按 source 限制并返回 LIMITED，不能标完整开发通过。

---

## 输出

### 分支 A（只开发：参数含 skip-test；被编排器调用时由 `/sprint-full`·`/sprint-batch` 透传 skip-test 落入本分支，test/bugfix/close 归编排器负责）

```
✅ /sprint-dev 完成（Sprint-{NNN} 开发阶段）

开发范围：{后端/前端/全部}

后端（仅获 related-test 授权时执行 TDD）：
- {列出实现的模块和接口}
- 单元测试：{真实结果；未请求为 NOT_REQUESTED}
- 编译验证：⏭️ 移至验收（/sprint-test 仅改动侧 + 资源受限执行）

前端：
- 公共组件：{列出新建/复用}
- 页面/组件：{N} 个
- 前端校验（lint + 类型检查，不打包）：⏭️ 移至验收（/sprint-test 仅改动侧 + 资源受限执行）

🔄 已更新：
- memory/{version}/{user}/activeContext.md

📌 下一步：
1. /sprint-test → 执行测试阶段
2. /sprint-bugfix sprint-{NNN} → 修复已知问题（如有）
```

### 分支 A/B 完整串联

```
🎉 /sprint-dev "{描述或编号}" 完成（Sprint-{NNN} 全流程）

{如分支 B，展示 Phase 0B 追加的文件清单}

各阶段摘要：
  Phase 0B 增量追加：✅ 完成（仅分支 B）
  Phase 0B.2 启动新 Sprint：✅ 完成（仅分支 B）
  Phase 1 开发：✅ 完成 — {摘要}
  Phase 2 测试：✅ 完成 — 通过 {N} / 失败 {N}
  Phase 3 修复：✅ 完成（{M} 轮循环，修复 {N} 个 bug）
  Phase 4 关闭：✅ 完成

📋 产出文件：
- docs/testing/{version}/sprint-{NNN}/
- docs/bugfix/{version}/bugfix-*-{user}.md（如有新 bug）
- memory/{version}/{user}/sprints/sprint-{NNN}.md

📌 下一步：
- /sprint-dev "<下个目标>" → 继续新增功能
- /sprint-bugfix → 修复零散 bug（无需新 Sprint）
- /version {version} → 发布版本
```

---

## 使用示例

```bash
# 场景 1：按计划被编排器调用（常见）
/sprint-full 001
# 内部会调用 /sprint-dev

# 场景 2：分步模式下的开发阶段
/sprint-start 001
/sprint-dev           # 默认实现+静态+相关单测；自动修复复验后终端返回
# 已授权父链中抑制自动串联可带 skip-test
/sprint-dev 001 skip-test

# 场景 3：★ 独立描述（默认 light，不累进）
/sprint-dev "新增用户导出功能"
# 默认light：实现 → 静态 → sprint-test → 必要修复/复验 → 终端；不创建Sprint

# 场景 4：只想开发不想自动测试
/sprint-dev "增加菜单缓存" skip-test

# 场景 5：只开发后端部分
/sprint-dev "重写权限模块" backend
```
