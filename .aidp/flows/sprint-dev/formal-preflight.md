# /sprint-dev — formal 通用参数、决策纪律、前置流程与 A/B 分流

> 本片覆盖：formal 通用参数、决策纪律、前置流程与 A/B 分流。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

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


按参数解析结果，只 Read `{{AIDP_HOME}}/flows/sprint-dev/formal-existing.md`（A）或 `{{AIDP_HOME}}/flows/sprint-dev/formal-increment.md`（B）。不得同时读取两路。
