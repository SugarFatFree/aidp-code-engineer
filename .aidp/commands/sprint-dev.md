# /sprint-dev — 开发阶段（独立可用，支持自动累进）

你正在执行 `/sprint-dev` 命令。

**★ 本命令支持两种调用方式**
- **方式 A（被编排器调用）**：`/sprint-full` / `/sprint-batch` 内部调用，执行当前 Sprint 的开发
- **方式 B（独立直接调用）**：用户直接调用，自动累进创建新 Sprint 并串联后续 `/sprint-test` → `/sprint-bugfix` → `/sprint-close`

**★ 本命令是编排器**：调用 `superpowers:test-driven-development`（TDD）+ `superpowers:subagent-driven-development`（并行开发）。

参数：$ARGUMENTS
- `/sprint-dev` — 开发当前进行中的 Sprint（从 activeContext 读取）
- `/sprint-dev 001` — 开发已规划的 Sprint-001（前提：已 /sprint-start）
- `/sprint-dev "新增用户导出功能"` — ★ 独立使用：自动累进新 Sprint 并执行全流程
- `/sprint-dev backend` — 仅后端开发（当前 Sprint）
- `/sprint-dev frontend` — 仅前端开发（当前 Sprint）
- `/sprint-dev "<描述>" backend` — 自动累进 + 仅后端
- `/sprint-dev 001 skip-test` — 跳过后续 test/bugfix/close 自动串联
- `--cascade-now` — ★ **跳过攒批、当场跑完约定 22 四级级联**（默认行为是把变更按族记入 `_开发期{族}增量.md`、留到收口点批量级联，见 `flows/sprint-dev/postdev-writeback-1.md` 步骤 3.8 + `{{AIDP_HOME}}/reference/开发期族增量.md`）。用于**当轮就要拿到自测用例**的场景——收口点不含 `/sprint-close`，当天开发当天关闭的 Sprint 靠它兜底
- `--dev-scale=S|M|L` — ★ **显式覆盖 Step X.0.0 的改动量档位判定**（S=小改动：L2 就地在既有册追加小节、不另起分册；M=现行全量级联；L=全量 + 部署基线联动）。不带则据本 Sprint 实际改动文件数 + 是否有接口/表/语义变更**自动判档**。⛔ 档位**只伸缩承载形态**，L1 需求留痕 / L4 自测用例 / 约定 22 检测项与触发级别 / 各类硬门**任何档位都不省**（详见 `flows/sprint-dev/postdev-writeback-1.md` 步骤 3.5）
- `--unattended` — ★ autopilot `/loop` 无人值守标记：Step 0 UI 门（C/D）、**Phase 0A.5 死代码决策门情形 C**、Step X.0.0 约定22 级联门、**约定28 引新库同意门**均**不弹 `AskUserQuestion`**，改**消费 PRD `autopilot_decisions` 预声明**（visual_baseline → A/B/C/D；约定22 默认自动级联；死代码情形 C 默认「① 并存切流量」；需引新库无栈支持 → 转失败处置熔断而非弹窗），避免 7×24 挂死（由 `/sprint-autopilot` → `/sprint-batch` → 本命令透传）
- `--from-batch` — 批量子任务标志（由 `/sprint-full` 透传）：本命令不弹 `AskUserQuestion`，内容决策门按「⏸ 待裁决」返回上层（语义单一信源 = `/sprint-full` 参数表）
  - ⛔ **`--unattended` 绝不弹任何交互门（catch-all，覆盖所有未枚举门）**：上面点名的 4 个门只是**举例**，不是穷举白名单。在 `--unattended` 下，**除本命令文档明确写出的「失败/熔断转人工」路径外，严禁 `AskUserQuestion`、严禁以任何形式停下征询用户**。**尤其严禁自发弹出「开发工作量较大 / 如何推进 / 我全自主完成 vs 先做某 Sprint 阶段确认 / 是否继续 / 要不要分阶段」这类范围·进度确认门**——本 Sprint（含累进产生的多个 Sprint）的全部前后端工作是**一个不可分割、必须一次做完的整体**，`--unattended` 本身即「把全部做完」的授权，**不得**以"工作量大 / 稳妥起见"为由降级为分阶段或征询。凡本应由用户拍板处一律走 PRD `autopilot_decisions` 预声明或文档化保守默认；确实无法自动解决的转失败处置（熔断冻结 + 继续/通知，见对应门），**绝不挂起等待用户输入**。

## ⛔ 统一决策纪律（交互式与 `--unattended` 同为硬约束，最高优先）

> 上一条对"自发范围/进度确认门"的禁止**不限于 `--unattended`**——**交互式（用户在场）下同样是硬约束**。无论哪种模式：

- **所有"文档同步 / 是否继续 / 如何推进"的决策，只能走命令文档明确定义的结构化门**（Step 0 UI 门、Phase 0A.5 死代码门、Phase 0B.1.1 完成硬门、Step X.0.0 级联门的破坏性变更确认等）。这些门要么按规则**默认自动执行不弹窗**，要么在**明确枚举的例外**下用 `AskUserQuestion` 给出**固定选项**。
- **严禁 agent 自由发挥式反问**——尤其禁止在开发中途或结尾自发抛出「开发工作量较大 / 要不要补设计文档 / 还是先这样 / 是否继续 / 要不要分阶段」等**非结构化、无预定义选项**的征询。本 Sprint 全部工作是一次做完的整体；文档补充是既定动作（Phase 0B.1.1 主路径 + Step X.0.0 兜底），**不是**可反问用户"要不要做"的选择。
- **交互式与无人值守的唯一差别**：仅在于**明确枚举的结构化门**（如 UI 的 C/D、死代码情形 C、级联的破坏性变更）交互式弹固定选项、无人值守消费 PRD 预声明；**除此之外，两种模式都不得自发停下征询**。凡文档未定义为"该弹窗"的地方，一律按保守默认自动推进。
- **★ 边界澄清：哪些"必须设结构化门"、哪些才是"禁止的自发反问"（防本纪律被误读为"一律别问"而省掉该设的门）**：本纪律禁止的是**无持久副作用、选项不可穷举**的进度/范围征询（"是否继续 / 要不要分阶段 / 要不要补文档 / 工作量大要不要我全自主"）——这些一律按保守默认自动推进、不问。但满足下列**正向判据任一**的动作，**必须**设结构化门（用 `AskUserQuestion` 给固定选项让用户拍板，属**合规的门、不受本纪律"禁自发反问"限制**）：
  1. **会产生持久目录结构**（新建 `docs/{version}/`、`memory/{version}/` 等版本级持久目录）；
  2. **会产生对外承诺**（版本号即 SemVer 兼容性承诺 / git tag / 版本分支等对外制品）；
  3. **不可逆或回退成本高**（已推送的 tag/分支、已分发的制品、`git mv` 一批目录才能撤销的结构）。
  典型如 **Phase 0B.0 版本落点决策门**（三条全中）：**绝不能以"不许自发问"为由跳过**。判定口诀：**动的是"要不要继续/怎么推进"→ 不问自动推进；动的是"版本号/持久目录/对外 tag 这类高成本不可逆承诺"→ 必须设门问用户**。
- **★ "缺陷/问题怎么修"的默认处置 = `/sprint-bugfix`「缺陷处置默认决策纪律」（单一信源，约定 21 不复述）**：开发/修复途中遇到具体缺陷（失败被伪装成成功、前端吞后端 error、上游不可达、上游已交付更优端点、安全 fail-open 等）时，**先问一句「不做这个修复，当前行为是不是错的？」——是→按纪律映射表默认处置【直接修、不问】、拿不准也默认修**；只有"口径/单位/默认值需产品定义""涉及版本号/tag/对外承诺"才归"必须问"。**严禁把本就该默认修的缺陷当成"要产品拍板"挂起等人**（下游反馈根因）。
- **★ 运行时验证纪律 = 约定 35（详规 `{{AIDP_HOME}}/rules/code.md`，约定 21 不复述）**：开发/验证代码**默认只静态验证**（类型/语法/lint/确定性脚本）；**绝不为"看 UI 效果 / 验证运行时"擅自启动前后端服务**（`npm run dev`/`vite`/`mvn spring-boot:run` 等——抢端口/冲突/卡机）**或跑完整构建**。需运行时/浏览器验证 → **(a) 已部署环境 / (b) 用户已运行服务（先探端口、有则复用绝不另起）/ (c) 都无先 `AskUserQuestion` 由用户启动**。**★ Bash 起任何常驻服务类命令前先自检**「是否用户显式要求 / 是否 `deployment.mode=local` 授权例外」，否则中止改走 (a)/(b)/(c)。

## 前置流程

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
  - 其余字符串（"xxx"）              → 分支 B：★ 自动累进新建 Sprint
  - 空                                → 分支 A：开发当前 Sprint
```

> ⛔ **控制 flag 那一行不可删**：`/sprint-full` Phase 2 调的就是 `/sprint-dev skip-test [--unattended]`
> （`skip-test` **裸在第一位**）。少了这一行，按上表逐字判定 `skip-test` 属"其余字符串" → 落进
> **分支 B**，于是在编排器已经启动过 Sprint 的情况下再取新号、产 6 类增量文档、
> 并再启动一次新 Sprint。而 `/sprint-full` 落在 `/sprint-batch` 与 autopilot 主链的**每一个
> Sprint** 上。对照 `/sprint-bugfix` 方式 C 传的是 `/sprint-dev {新NNN} skip-test`（数字在前）故不受影响
> ——**只有 `/sprint-full` 这一处是裸传**，本行就是为它写的。

---

## 分支 B：自动累进新建 Sprint（★ 独立使用）

### Phase 0B.00：★ 约定 9 前置门（⛔ 最先跑，先于版本落点门与任何取号动作）

> 存在**未关闭 Sprint** 时**立即停下**要求先 `/sprint-close`，⛔ 不得继续。
> **不能等到 Phase 0B.2 的 `/sprint-start` 才拦**——那时 Sprint 号已被 `check_sprint_numbering.py next` 消耗、
> 六类 `NN_*.md` 增量已落盘；close 后重跑会拿到**又一个**新号，
> 上一轮产物成为无 Sprint 归属的孤儿。而独立分步执行时这些副作用根本不会发生。
> 判据与话术同 `/sprint-full` Phase 0B.0 前自检（那条已落地，本条照它办）。

### Phase 0B.0：★ 版本落点决策门（单一信源 —— 累进前置，最先跑，先于任何持久副作用）

> **要解决的问题**：一个版本**已发布**（已归档、已打 tag、已建版本分支、已推送）之后、用户**尚未主动开始新版本规划**时，又提出新需求 / bug 修复。此刻执行体**绝不能自行裁量版本号**（如"向后兼容 → 就 patch"）**更不能静默创建新版本目录骨架、也不能静默往已发布版本累进**——版本号对外是 **SemVer 兼容性承诺 + 发布节奏**（产品/运维决策，非技术判断），re-release 还会**移动已推送的 tag**（有实际风险）。必须让用户**先选落点**。
>
> ⚠️ **本门是结构化决策门、不受「⛔ 统一决策纪律」的"禁自发反问"约束**——它满足该纪律「必须设门的正向判据」全部三条（会建持久目录 / 会产生对外承诺〔版本号·tag·分支〕/ 不可逆或回退成本高〔已推送 tag·分支〕，见本命令「⛔ 统一决策纪律」段正向判据）。**绝不能以"不许自发问"为由省掉本门**（下游越权正是这条纪律被误读为"一律别问"所致）。

**① 检测「当前版本已发布 且 未开始新版本规划」**（命令端 Bash，`{V}` = `AGENTS.md`「当前状态.当前版本」）：
```bash
V={version}                 # 形如 V0.2.0
VNUM=${V#V}                 # 去 V 前缀 → 0.2.0
# 已发布信号（任一命中即已发布）：① 该版本存在 release tag（三风格全覆盖，与 version.md「tag 风格识别约定」同口径）
# ⛔ 必须区分「判定失败」与「判定为未发布」：两者都产出空值时，浅克隆 / 未 fetch --tags /
#    CI 无 tag 检出 / git user.name 与 memory 目录名不一致 / progress.md 格式不符 —— 任一情形
#    都会静默判"未发布"并累进，即把"版本未发布"当默认假设、不实际判定。
TAG_OK=1; git rev-parse --git-dir >/dev/null 2>&1 || TAG_OK=0
git fetch --tags --quiet 2>/dev/null || true          # 拿不到远端 tag 不致命，但要试一次
TAGS=$(git tag -l "v$VNUM" "V$VNUM" "$V" "release-$V" "release-v$VNUM" 2>/dev/null) || TAG_OK=0
RELEASED=$(printf '%s\n' "$TAGS" | head -1)
# ③ 第三信号（不依赖 tag 与文件名约定）：baseline 的 internal_released_at + 随 tag 冻结的部署基线
[ -z "$RELEASED" ] && [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" get internal_released_at --default "" 2>/dev/null)" ] && RELEASED="internal_released_at"
[ -z "$RELEASED" ] && [ -d "docs/deployment/$V/配置文件/全量" ] && RELEASED="deployment-baseline"
# ② progress.md「版本历史」/ 版本更新日志 标本版「✅ 已发布」
[ -z "$RELEASED" ] && grep -qsE "$V.*✅ ?已发布|已发布.*$V" "memory/$V/$(git config user.name)/progress.md" 版本更新日志.md 2>/dev/null && RELEASED="$V(状态已发布)"
# ⛔ fail-closed：tag 判定本身失败且其余信号均未命中 → 落点未知，按「已发布」进下方决策门，⛔ 不并入"未发布"
[ "$TAG_OK" = 0 ] && [ -z "$RELEASED" ] && RELEASED="unknown(tag-query-failed)"
echo "RELEASED=${RELEASED}"
```
> ⛔ **`TAG_OK=0`（不是 git 仓库 / tag 查询本身失败）→ fail-closed**：上方最后一行把 `RELEASED` 置为 `unknown(tag-query-failed)`，
> 于是走下方决策门（交互式让用户确认版本落点；`--unattended` 按保守默认处理并留痕），⛔ 不得并入"未发布"直接累进。
>
> 说明：若用户已开始新版本规划，「当前版本」早已被 `/version` 推进到未发布的新号（无 tag、状态非已发布），本门 `RELEASED` 为空、**自动不触发**——故本门只在「停在已发布版本、又来新需求」时才拦。

**② ★ 决策前置铁律（不可逆序）**：`RELEASED` 非空时，**在用户选定落点并确认之前，绝不创建任何 `{新版本}` 持久副作用**——不 `mkdir docs/requirements/{新版本}/` / `docs/design/detail/{新版本}/` / `memory/{新版本}/`、不写项目记忆文件「当前状态」、不建 tag/分支。**决策 → 用户确认 → 才建目录**（事前一问，成本远低于事后 `git mv` 一批目录 + 回改状态文件）。

**③ `RELEASED` 非空 → 决策门（`RELEASED` 为空 → 跳过本门，直接进 Phase 0B.1 正常累进）**：
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

### Phase 0B.1.1：★ 自动文档增量流

**触发条件**：分支 B 必跑（除非参数含 `skip-doc-sync`）。

**★ 单一权威路径（Phase 0B.1.1 ↔ Step X.0.0 的关系与衔接，消除"两头落空"）**：
- **分支 B（口述累进）下，Phase 0B.1.1 是文档同步的唯一主路径**——"先补文档、后写代码"，本步 6 类补充（研发需求 / 详细设计 / 接口设计 / 数据库设计 / 研发执行计划 / 研发自测用例）**在进入 Phase 1 开发前必须已生成并登记**，不得延后、不得指望末段 Step X.0.0 兜。
- **末段 Step X.0.0 在分支 B 下只是"兜底增量"**：仅捕捉 Phase 0B.1.1 完成**之后、开发过程中又新冒出**的额外漂移（临时加的接口/字段/规则）。它**不是**分支 B 补文档的主战场（分支 A 才是），**更不允许**把 Phase 0B.1.1 应做的 6 类补充推迟到 X.0.0——那会造成"0B.1.1 觉得 X.0.0 会补、X.0.0 觉得 0B.1.1 已补"的两头落空。
- **铁律**：分支 B 必须先跑完 Phase 0B.1.1（含下方硬门）再开发；X.0.0 只增量、不接管。二者共用同一套 `NN_<业务主题>.md` 补充文档体系（约定 15）与约定 22 级联链，**绝不重复生成同一批增量、也绝不互相甩锅**。

**典型场景**：产品口述新功能 → 研发用 `/sprint-dev "<描述>"` 直接开发 → 历史问题是只追代码不追文档 → 现在用本流程自动追平。

**步骤**（8 步串行，含 2.5「`--scale` 派生」与 3bis（独立一步、不能并进步骤 3）；任一步失败暂停并要求用户处理，不静默继续）：

1. **记录口述补充**：把命令参数 `"<描述>"` + 当前时间 + git user 写入新文件：
   `docs/requirements/{version}/产品提供/口述补充-{YYYYMMDD-HHMM}.md`（每次累进一份；用时间戳区分多次口述；该目录已有 PRD 时本文件作为同级补充）

2. **生成研发需求补充**：经 `/sprint-requirements {version} --supplement={NN} [--unattended]` 编排（研发需求唯一入口，内部调 `ux-logic-extractor` skill 增量补充、prompt 驱动；★ **不直调 SKILL**——直调会跳过命令端的落盘归一 / 多系统拆分 / 头部元数据表 / AIDP 硬规范回检，与同轮其余三层 `/sprint-design --supplement [--unattended]` · `/sprint-plan --supplement [--unattended]` · `/sprint-selftest --supplement [--unattended]` 走命令中介保持一致），输入：
   - 口述补充文件（步骤 1 产出）
   - 当前 `docs/requirements/{version}/研发需求/01_研发需求.md`（既存基线；历史裸 `00_研发需求.md` 兼容）
   - 当前 `docs/prototype/{version}/code/` + `mockup/`（如有，作为交互细节参考）

   输出研发需求增量文档（NN 按目录现有序号累进），并在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间）。

   > ★ **增量文档命名（按约定 15）**：所有增量文档统一 `NN_<业务主题>.md`（NN 续编目录现存最大序号 +1，排除 `00_索引`/`98_`/`99_`）——**文件名不带"补充"字眼**；补充身份只记入 `00_索引.md`（类型=补充 + 更晚生成时间）。上游 SKILL 本就产出干净 `NN_<业务名>.md`（已禁"补充/追加"语义前缀，各 SKILL 的 `check_doc_split.py` 亦禁），命令端**只做序号续编校正、绝不回补"补充"字眼** + 维护 `00_索引.md`（脚本见 `{{AIDP_HOME}}/flows/version/planning-4.md`（`version.md` Step 2.4.4 现仅是一行指针））。下文括注（如"研发需求增量"）仅标识增量内容所属文档类型。

   skill 内置的不中断原则、数据闭环完整性等会自动生效（沿用主文档 `Q-NNN` 编号空间往后递增，数据闭环孤立端用 `Q-FLOW-NNN`），命令端按 AGENTS.md 约定 21 不复述具体条款，详见 `{{AIDP_HOME}}/skills/ux-logic-extractor/SKILL.md`。

2.5. **★ 口述规模档位判定门（`sup_scale`）——【必跑】，下面步骤 3 / 3bis / 4 的 `{档位}` 就是它的产出**

   > ⛔ **本步不可省**：步骤 3 / 3bis / 4 三处都写 `--scale={档位}`，而 `{档位}` **只有本步生产**。
   > 不判就传不出去，三个下游 SKILL 全部**缺省回退 L 档全套**——正文一行不少，
   > "小改动不走大流程"整个失效（下游实证：6 个源文件、零建表、零 SQL、零配置项、零新增端点的一轮，
   > 产出 762 行四层规划文档，文档:代码 ≈ 5:1）。

   **判据（与 `/version` Step 2.4.1.5「需求规模档位」同构，据步骤 2 产出的研发需求增量确定性计算）**：
   `REQ_COUNT`=本轮增量的研发需求条目数 · `PAGE_COUNT`=涉及页面/原型数 · `HAS_DDL`=是否新建表 ·
   `HAS_API`=是否新增接口端点 · `HAS_CONFIG`=是否新增配置项 · `THIRD_PARTY`=四值（取值与判法**完全复用**
   Step 2.4.1.5 的表，本处不复述）。

   | 档位 | 判据 | 承载形态 |
   |------|------|---------|
   | **S** | `REQ≤5 且 PAGE≤2 且 !HAS_DDL 且 THIRD_PARTY ∈ {none, field-level}` | 设计合并 1 册；**允许就地在既有册追加小节、不另起 `NN_` 分册** |
   | **S（语义子档）** | 见下方独立判据 | 同上 **+ 强制产出「受影响结论清单」** |
   | **M** | `REQ≤15 或 PAGE≤5`（未命中 S），或 `THIRD_PARTY = endpoint-level` | 3 册（详设/接口/数据库）|
   | **L** | 超出 M，或 `HAS_DDL`，或 `THIRD_PARTY = new-system` | 现状全套 |

   **★ S（语义子档）——「语义变更」不一刀切抬档**：
   `HAS_SEMANTIC=true` 但同时满足 **`REQ≤5` 且 `!HAS_DDL` 且 `!HAS_API` 且 `!HAS_CONFIG` 且改动面 ≤6 个源文件**
   → **判 S 档**，但**强制产出「受影响结论清单」**（下方）。
   > **Why**：原判据把「语义变更」当成一个**布尔**、命中即抬到 M——可"一个展示占位值从 `—` 改成 `0`"
   > 与"新建一个业务域"被判成同一档。语义变更的**影响面明确、可枚举**，该管的是"有没有逐条清算"，
   > **不是"要不要另写 762 行册子"**。这与 `THIRD_PARTY` 已经从布尔改成四值是同一个教训。

   **★「受影响结论清单」（S 语义子档的强制伴生项，把"详略度"与"级联完整性"解耦）**：
   在研发需求增量里产一张表，**逐条打勾**、不得只写整体描述：

   | # | 受影响落点 | 位置 | 旧结论 | 新结论 | 处置 |
   |---|---|---|---|---|---|
   | 1 | 需求条目 / ADR / 用例断言 / 反向断言 / 铁律注释 / `REQ-XXX` 代码注释 | 具体文件:行 | … | … | 失效 / 改写 / 不受影响 |

   > ⛔ **清单不是"档位的一部分"、是"级联保证的一部分"**：档位只伸缩**写多少**，
   > 约定 22 的检测项与触发级别、L1 需求留痕、L4 自测用例产出**任何档位都不省**。
   > 本清单存在的意义正是：**降档不降级联**。

   - **落盘留痕**：写 baseline `versions.{V}.sprints.{新NNN}.sup_scale`
     （`{tier, req_count, page_count, has_ddl, has_api, has_config, has_semantic, third_party, source:"auto"|"user", at}`）。
   - **用户覆盖**：`/sprint-dev "<描述>" --dev-scale=S|M|L` 显式覆盖（留痕 `source:"user"`）。
   - **打印**：`📐 口述规模档位：S（REQ=3 PAGE=1 建表=否 接口=否 配置=否 语义=是 第三方=none）→ 设计就地追加小节 + 受影响结论清单`。
   - **⛔ 判出的档位必须真的传下去**：步骤 3 / 3bis / 4 的 `--scale=` 一律填本步结果；
     只写进 baseline 而不传给 SKILL = 白判一次档（与 Step X.0.0 步骤 3.5 同一个坑）。

3. **触发增量设计**：调 `/sprint-design {version} --supplement={NN} --scale={档位} [--unattended]` 派生增量设计：
   - Step 0.6.4.7 全扫 code/ 拿当前代码现状（含本 sprint 即将新增功能可能已部分实现的情形）
   - Step 0.3 按四象限对比口述新功能 vs 代码现状：判定走"② 新增"还是"③ 代码超前-补写"
   - 以增量 prompt 驱动调 dev-logic-architect（按其 SKILL 增量约定，无 mode 参数）产出详细设计 / 接口设计 / 数据库设计的补充文档（均归一为 `NN_<业务主题>.md`，按实际范围）
   - **★ 路径占位符显式传参**：调 dev-logic-architect 补充时，必须显式传 §2.5.7 的 5 个占位符值（`{SQL脚本目录}=code/sql/`、`{文档目录}=docs/design/detail/`、`{API文档目录}=docs/design/detail/`、`{测试文档目录}=docs/testing/`、`{配置目录}=env/+docs/deployment/{version}/`），禁止 SKILL 自动推断；映射表权威见 `docs/init/06_版本与用户目录约定.md` §2.5.7

3bis. **★ 触发增量研发执行计划（独立一步，不能并进步骤 3）**：调 `/sprint-plan {version} --supplement={NN} --scale={档位} [--unattended]` 产出 `docs/plans/{version}/NN_<业务主题>.md`。
   > ⛔ **`/sprint-design` 不产研发执行计划**——它全文不涉及 `dev-execution-planner`，其补充模式产物只有 详细设计 / 接口设计 / 对外开放接口 / 数据库设计 / DDL SQL 五类。⛔ 因此**不得把"计划增量"并进步骤 3**——那会让下方硬门第 6 项（**不可 N/A 的必 Pass 项**）无人生产、恒 Fail。成因见 `{{AIDP_HOME}}/flows/sprint-dev/rationale.md`「计划增量为何必须独立一步」。
   > 即便临场改为直调 `dev-execution-planner` 兜住，也会绕过 `/sprint-plan` 的 Step 1.5 三脚本回检、Step 1.6 SQL 路径回写、Step 2 关联文档注入——故必须走命令编排、不得直调 SKILL。

4. **★ 同步更新研发自测用例**：经 `/sprint-selftest {version} --supplement={NN} --scale={档位} [--unattended]` 编排（研发自测唯一入口，内部调 `dev-manual-testcase` skill 增量补充，prompt 驱动），输入：
   - `NN_<业务主题>.md`（研发需求增量，步骤 2 产出，本次新增 / 修订的功能点）
   - `NN_<业务主题>.md`（详细设计 / 接口设计 / 研发执行计划增量，步骤 3 产出，与功能点关联的接口/页面/任务）
   - 原研发自测用例（`研发自测/02_自测用例-总览.md`（多文件）或 `研发自测/02_全量自测用例.md`（单文件）；研发自测方案 `研发自测/01_研发自测方案.md`；旧锚布局兜底 `研发自测/01_自测用例-总览.md`·`研发自测/00_研发自测方案.md`·`研发自测/00_研发自测.md`；基线，只读）
   - `code/` 已有代码
   - **★ 路径占位符显式传参**：必须显式传 `{测试文档目录}=docs/testing/`（覆盖 SKILL 默认 `docs/test/`；映射表见 `docs/init/06` §2.5.7）

   skill 工作要求：仅针对本轮新增/修订的功能点输出新用例或修订用例，未变功能不重复；原型变更必须重新对齐"操作对象 + 预期现象"。skill 内置的数据一致性与溯源原则 + 上游引用规则会自动生效，命令端按 AGENTS.md 约定 21 不复述，详见 `{{AIDP_HOME}}/skills/dev-manual-testcase/SKILL.md`。

   输出 `docs/testing/{version}/研发自测/<NN>_<业务主题>.md`（按 AGENTS.md 约定 15 统一数字前缀规则：NN = 目录现存最大序号 + 1、用例从 `02_` 起，文件名不带"补充"字眼；★ **一律在 `研发自测/` 同目录平铺续编、严禁再拆二级子目录**——SKILL「文件命名总则」要求同目录 `NN_` 前缀平铺，其硬门 `check_testcase_format.py` 只 `glob("*.md")` 非递归，落进子目录的用例会整体逃检），并在**研发自测专职索引** `00_索引.md`（及 `01_研发自测方案.md` 的「用例索引」段 / `02_自测用例-总览.md`）追加登记该增量（研发自测目录已对齐通用范式、导航锚 = `00_索引.md`，见约定 15）。新增用例 ID 全局唯一（继承原主文档编号空间，往后递增）。

   **跳过条件**：步骤 2 的研发需求补充内容仅包含纯技术内部调整（如 SQL 索引优化、性能调优）且未触达任何用户可见功能 → 终端 WARN 并跳过；否则**不可跳过**。

5. **更新各目录导航锚**：本轮新增的 6 类增量文档在对应目录导航锚各追加一行（类型=补充 + 生成时间）——研发需求 / 详细设计 / 接口设计 / 数据库设计 / 研发执行计划 / **研发自测用例**均 → `00_索引.md`（研发自测已对齐通用范式，另在 `01_研发自测方案.md` §8 用例索引段同步登记业务导航）

6. **完成报告**：终端打印「口述补充已转化为研发需求补充（`NN_<业务主题>.md`）+ 设计补充 + 计划补充 + **研发自测用例补充**；本 Sprint-{新NNN} 即将基于此增量基线开发」

**★ Phase 0B.1.1 完成硬门（Pass/Fail — 任一 Fail 不得进入 Phase 1 开发、不得输出"开发完成"）**：

> 参照 `/sprint-plan` / `/version` 末段硬门表：分支 B 的"自动文档增量流"必须逐项 Pass 才放行开发；命令端在离开 Phase 0B.1.1 前逐条自检（可用 `ls`/`grep` 客观验证文件与索引登记），**任一 Fail → 停下补齐该项，绝不带病进开发、更不得在末尾对用户反问"要不要补设计文档/还是先这样"**（那属被禁的自发确认门，见文首硬约束）。

| # | 校验项 | Pass 判据 | Fail 处置 |
|---|--------|-----------|-----------|
| 1 | 口述补充落盘 | `docs/requirements/{version}/产品提供/口述补充-*.md` 存在且非空 | 补写步骤 1 |
| 2 | 研发需求补充 | `docs/requirements/{version}/研发需求/NN_*.md`（本轮 NN）已生成 | 回步骤 2 重跑 `ux-logic-extractor` |
| 3 | 详细设计补充 | `docs/design/detail/{version}/NN_*.md`（详细设计）已生成 | 回步骤 3 重跑 `/sprint-design --supplement [--unattended]` |
| 4 | 接口设计补充 | 本轮涉及接口 → 接口设计增量已生成；不涉接口 → 标 N/A | 涉接口却缺 → 回步骤 3 |
| 5 | 数据库设计补充 | 本轮涉及表/字段 → 数据库设计增量已生成；不涉库 → 标 N/A | 涉库却缺 → 回步骤 3 |
| 6 | 研发执行计划补充 | `docs/plans/{version}/NN_*.md`（研发执行计划增量）已生成 | 回**步骤 3bis** 重跑 `/sprint-plan --supplement [--unattended]`（⛔ 不是步骤 3，`/sprint-design` 不产计划） |
| 7 | 研发自测用例补充 | `docs/testing/{version}/研发自测/NN_*.md` 已生成（纯技术内部调整走步骤 4 跳过条件 → 标 N/A + 记录原因） | 涉用户可见功能却缺 → 回步骤 4 |
| 8 | 各目录 `00_索引.md` 登记 | 上述已生成的增量在对应目录 `00_索引.md` 均有"类型=补充 + 生成时间"登记行 | 缺登记 → 回步骤 5 补登记 |

- **N/A 合法**：项 4/5/7 在本轮确无对应变更时标 N/A（附一句判据，如"本轮无接口变更"）即算 Pass；项 1/2/3/6/8 为**必 Pass 项**，不可 N/A。
- **★ S 档「就地追加」同样算 Pass（配合步骤 2.5）**：步骤 2.5 判为 **S 档**时，项 2/3/6 的 Pass 判据放宽为
  「**新建 `NN_*.md`** 或 **既有册中本轮新增小节 + 该目录 `00_索引.md` 生成时间已刷新**」二者取一——
  ⛔ 但**"两者都没有"永远是 Fail**：S 档降的是**承载形态**，不是"可以不留痕"。
  S 语义子档另加一项必 Pass：**「受影响结论清单」已产出且逐条有处置结论**（空表 / 只写整体描述 = Fail）。
- **`skip-doc-sync` 例外**：显式带该参数时本硬门整体跳过（见下方「跳过」），但须在完成报告显式 WARN 漂移风险。
- **无人值守（`--unattended`）同样受硬门约束**：Fail 项按上表"Fail 处置"自动重跑对应 SKILL；重跑仍 Fail → 转失败处置（熔断冻结 + #4 里程碑通知 WARN），**不挂起、也不放行带病开发**。

**跳过**：参数含 `skip-doc-sync` → 仅做步骤 1（记口述）；步骤 2~6 与上述完成硬门跳过。⛔ **但必须同轮把本轮口述变更按条目行格式写进【受影响各族】的增量册**（四族落点见 `{{AIDP_HOME}}/reference/开发期族增量.md`；终端 WARN 不落盘 = 欠账不可发现：`commit_gate::pending_cascade`、`check_cascade_landing.py`、四个收口点**全部只扫这四份册子**；不写则用户直接走 `/version` 发布时，收口点 3 的必删门会因「册子不存在」判为合法终态放行，即带着待级联条目走到版本发布）。此外终端 WARN「已跳过文档增量流，本 Sprint 完成后请人工跑 `/version` 补充模式校对；不跑会让设计/代码持续漂移」

### Phase 0B.1.3：★ 开发期口述追加 / 口径反转的处理（约定 34 ⑥ 决策门）

> ★ **单一信源，`/sprint-full` 模式 B Phase 0B.3 同用**（它只做编排触发、不复述本处判定）。

> **本门可在分支 B 的任意时点触发，包括 Phase 0B.1.1 已跑完、开发已经开始之后**——产品在同一轮里追加第 N+1 条口述、并且**反转**了上午刚写进文档的结论，是真实高频场景（下游实证）。原流程假定「口述 → 一次性写四层文档 → 开发」是线性的，**没有描述"文档已写完、开发已开始，此时口述追加或反转"该怎么办**，执行体只能自行决定"重跑 0B.1.1（重复生成）还是就地订正（不知道哪些段落失效）"。本门补上这段。

**触发**：Phase 0B.1.1 完成后（含开发进行中），用户 / 产品又给出新的口述内容。

**步骤 1 — 先判「追加」还是「反转」（不判定就动手 = 本门最常见的失效）**

| 判定 | 判据 | 处置 |
|---|---|---|
| **追加** | 新口述**只增加新结论**，不与任何已写入文档的结论矛盾 | 走常规增量：按 Phase 0B.1.1 步骤 2~5 追加（受**步骤 2.5 档位门**约束，小改动不另起分册）|
| **反转** | 新口述**推翻了已写入文档的既有结论**——口径反向 / 白名单方向调转 / 默认值·状态机·权限范围改写 | **必走下面步骤 2~4，一步不省** |

**步骤 2 — 失效结论清算（逐条打勾，⛔ 不许靠"重跑一遍 0B.1.1"代替）**

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

**步骤 3 — ⭐ 强制回答一个问题（本门最不可省的一条）**

> **「旧口径下被判定为安全 / 无害的设计，在新口径下是否仍然安全？」**

**口径反转会在一行代码都不改的情况下改变安全等级。** 下游实证：某 resolver 的 fail-closed，旧口径下判据源失败只会把资源误标 ⇒ 后果是**展示错误**；口径反转后，同一处误标立刻变成「本该统一开通的资源上出现**可用的解绑按钮**」，而解绑在上游是永久取消、不留恢复快照 ⇒ **不可逆数据破坏**。详设里那句「⛔ 不会误放行解绑」若不重写，就成了误导后人的**错误结论**。

**⛔ 这个问题不会被任何静态检查发现**——没有脚本能判"安全等级变了"。必须在本步显式回答并把结论写进详细设计的对应 ADR；答案为"不再安全"时，**当轮补齐守卫**（不得留到下个 Sprint）。

**步骤 4 — 用显式作废标记，不用静默改写**

- 被推翻的条目：原地加 `⛔ 本条已于 sprint-{NNN} 反转，改见 REQ-XXX / ADR-XXX`，**保留原文**再写新结论。
- 整册被推翻的：在该册头部加**整册作废标记**并指向新册。
- ⛔ 直接把旧文字改掉 = 代码注释里引用的旧编号无处可查，后来者只能按旧印象改回去。

**完成判据**：步骤 1 判定结论 + 步骤 2 清算表 + 步骤 3 的安全性回答，三者都写进本轮 `docs/requirements/{version}/产品提供/口述补充-*.md` 或研发需求增量；缺任一项不得继续开发。

### Phase 0B.2：启动新 Sprint

```
执行：/sprint-start {新NNN} [--unattended]（无人值守时透传）
```

### 转入共用「Phase 1 开发执行」段（本命令核心）

分支 B 不另设开发步骤、也不另设串联步骤：跳到下方「## Phase 序列（分支 A / B 共用）」，从 `Phase 1 开发执行` 起逐项执行到 `Phase 2-4 自动串联后续`（**串联规则的单一信源 = 该段的 `### Phase 2-4`**，本分支不复述、不改判定）。

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

> **目的**：开发新页面/接口前，先识别历史版本是否存在**同名/同语义**的死代码。判定为死代码 + 本 Sprint 重做该板块时，**必须先删旧再写新**，禁止叠加。详细判定规则与 grep 脚本见 `{{AIDP_HOME}}/agents/frontend.md` 核心原则 11 + `{{AIDP_HOME}}/agents/backend.md` 核心原则 11；本步骤仅做命令编排（按约定 21 不复述规则）。

**1. 识别本 Sprint 涉及的功能板块**（从设计/需求/计划读取）：

```bash
# 从研发需求 / 详细设计 / 研发执行计划提取本 Sprint 要做的板块/页面/接口名清单
SPRINT_NNN=$(cat memory/{version}/{user}/activeContext.md | grep "当前 Sprint" | awk -F: '{print $2}' | tr -d ' ')
grep -A 50 "Sprint-${SPRINT_NNN}" docs/plans/{version}/01_研发执行计划.md \
  | grep -E "新增|实现|开发|重做|重构" \
  | head -30
# 输出疑似涉及的"业务关键词"清单（如：用户管理、订单导出、报表中心）
```

**2. 对每个业务关键词跑死代码扫描**（按 agents/frontend.md + backend.md 核心原则 11 中的 4 信号脚本）：

输出 `memory/{version}/{user}/sprints/sprint-{NNN}-deadcode-scan-{YYYYMMDD-HHMM}.md`：

| # | 业务关键词 | 旧文件路径 | 信号①无菜单 | 信号②无 import | 信号③无路由/调用 | 信号④需求重做 | 归类 | 处置情形 |
|---|----------|-----------|-----------|---------------|----------------|--------------|------|---------|
| 1 | 用户管理 | `src/views/UserManage.vue` | ✓ | ✓ | ✓ | ✓ | 死代码 | B 删旧重做 |
| 2 | 用户管理 | `src/store/userManage.ts` | n/a | ✓ | n/a | ✓ | 死代码 | B 删旧重做 |
| 3 | 订单导出 | `controller/OrderExportController.java` | n/a | ✗（仍被引用） | ✗ | ✓ | 仍在用+需求重构 | **C 弹问询** |
| 4 | 报表中心 | `src/views/ReportCenter.vue` | ✗（菜单仍有） | ✗ | ✗ | ✗ | 仍在用 | A 增量增强 |

**3. 决策门**（按 3 类处置规则）：

| 情形 | 默认行为 | 是否弹 AskUserQuestion |
|------|---------|----------------------|
| **A 仍在用 + 增量增强** | 按约定 28 复用，正常往下写 | 否 |
| **B 死代码 + 重做（默认）** | `vcs_mode=git` 自动 `git rm`；`vcs_mode=none` 对已确认归类为 B 的旧文件逐项 `Path.unlink()` 本地删除（仅文件，不删未核对目录，缺失文件如实记录），含连带文件；同步补 `99_回滚脚本.sql` DROP（如涉及表） + 在 `*事实清单.md` 「死代码删除清单」段追加表格 | 否（默认无问询，避免打扰用户） |
| **C 仍在用 + 需求重构** | 弹 `AskUserQuestion`：「① 并存切流量（推荐）/ ② 直接替换 / ③ 单写新版保留旧版」三选一 | **是** |

★ **关键铁律**：归类为 B 的文件必须**在 Phase 0A.5 内完成实际删除**（`vcs_mode=git` 用 `git rm`；`vcs_mode=none` 经 Python `Path.unlink()` 删除已确认的本地文件，并用文件存在性复核），**不可**留待开发执行步骤里"边写边删"——否则 Agent 可能误以为"旧文件仍存在所以可以叠加"，反而触发反模式。

★ **情形 C 的 `--unattended` 降级（无人值守不挂死）**：`/loop` 无人值守（带 `--unattended`）下情形 C **不弹 `AskUserQuestion`**——优先消费 PRD `autopilot_decisions` 死代码处置预声明；无预声明则取**保守默认「① 并存切流量」**（新版并存 → 切流量 → 旧版留待人工删除，最不破坏现网），并在终端 + autopilot #4 里程碑通知 WARN「死代码情形 C 走无人值守默认①，旧版删除待人工复核」，**绝不挂起等待**。仅交互式（无 `--unattended`）才弹三选一。

**4. 表数据安全检查**（情形 B 涉及后端 Entity / Mapper 删除时必跑）：

```bash
# 读 memory/databaseBaseline.md 确认该表是否在基线中
grep "<旧表名>" memory/databaseBaseline.md
# 命中 → 询问用户"该表是否有生产数据"
#  - 有生产数据 → 升级到情形 C（不可直接 DROP TABLE）
#  - 无生产数据 → 在 99_回滚脚本.sql 同步加 DROP TABLE
# 不命中 → 该表是本 Sprint 才规划，无生产数据，可直接 DROP
```

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

> ⚠️ 关键规则一句提醒：**Step X.0.0 是约定 22「上游文档级联同步」的统一入口**——开发引入超出既存文档范围的实质变更（新增接口/表/业务规则/页面/功能点、原型字段被覆盖/裁剪、Mock→真实、语义·口径·范围变更）时必须按 4 级触发（研发需求→详细设计→研发执行计划→研发自测用例）自动级联，**禁止绕过它直接调单一 SKILL 补单层**；Step X.7/X.8 是约定 25 配置项清单 + 部署流程 SOP（检测驱动、独立于配置变更）。

> ⛔⛔ **详细步骤已外置为 3 个分片、进入本回写段的【第一动作】= 按需加载**：Step X.0.0–X.8 的完整步骤在 `{{AIDP_HOME}}/flows/sprint-dev/` 下 **3 个分片**，**进入本段第一动作 = 按序 Read 三片**、逐项执行：
> 1. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-1.md`** — Step X.0.0（上游文档级联同步检测）
> 2. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-2.md`** — Step X.0 / X.2 / X.3 / X.4 / X.5 / X.6 / X.7
> 3. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-3.md`** — Step X.8（部署流程 SOP + SQL执行台账）+ **累进路径的产物审计收口**
>
> 下方骨架仅供定位，**权威判定与触发条件一律以分片 flow 文件为准，绝不凭本骨架或记忆略过任一 Step，也不得只读其中一片**。

**触发条件（详见 flow 文件）**：开发引入 新增/改接口 · 新增表/改表结构/新增字段 · 新增公共组件/页面/模块 · 新增外部依赖 · 调整 context-path/端口/proxy/API 前缀（配置事实）· 开发期发现"需求漏项" 任一即触发回写。

**回写步骤骨架（详见 `postdev-writeback-1.md` + `-2.md` + `-3.md`）**：

| Step | 作用（一句话） |
|---|---|
| **X.0.0** | ★ 上游文档级联同步检测（约定 22 统一入口，4 级触发 + 默认攒批入台账；**仅破坏性变更弹确认门**——普通级联已改为默认自动、无「跳过」口子）|
| **X.0** | 研发需求回写（含开发期需求漏项）|
| **X.2** | 调 dev-logic-architect 更新设计（走 `/sprint-design --ledger-cascade [--unattended]` 编排；⛔ **不是 `--supplement={NN}`** —— 本段是约定 22 收口级联，就地改主文档、不新建分册，落点门会判 exit 1）|
| **X.3** | 调 `/sprint-plan --ledger-cascade [--unattended]` 更新研发执行计划（⛔ 同上，不是 `--supplement`）|
| **X.4** | 更新项目级 memory（架构级变更时）|
| **X.5** | 更新 SQL 脚本 |
| **X.6** | ★ 更新 *事实清单.md（配置事实变更时）|
| **X.7** | ★ 维护配置项清单（约定 25）|
| **X.8** | ★ 部署流程 SOP + SQL执行台账（约定 25，检测驱动、独立于配置变更）|
| **X.8 收口** | ★ 累进路径的产物审计（本轮产出四类文档任一份 → 派 version-auditor 子 Agent；⛔ 无人值守不得跳过）|

> 收口：回写段完成 → 进入下方「完成前验证」。**执行前务必已按序 Read `postdev-writeback-1.md` + `-2.md` + `-3.md` 并按其逐项完成，不能只看本表。**

---

### 完成前验证

调用 `superpowers:verification-before-completion`：
- 确认本 Sprint 范围内代码已实现、无遗留 TODO
- ★ **不在开发阶段逐任务编译/校验**——后端编译 / 前端校验（lint + 类型检查，**不打包**）已收敛到 **Sprint 验收（`/sprint-test`）**，届时**仅处理本 Sprint 改动的一侧**（改前端才校验前端、改后端才编后端）且以**资源受限方式**执行（`nice` + 限并发，避免 CPU 打满），配方见 `agents/backend.md`「Step 7」/ `agents/frontend.md`「Step 4」。前端验收期只做 lint + 类型检查、**不跑完整打包**，部署打包由使用者按需自行执行。分支 A（skip-test 只开发）则编译/校验推迟到后续 `/sprint-test`

更新 `memory/{version}/{user}/activeContext.md`：
- 在「子迭代记录」中追加开发阶段的 Round 记录
- 在「已完成工作」中追加完成项
- 更新「当前工作焦点」为"开发完成，等待测试"

> ★ **若本命令触发 `git commit`**（自动提交场景）：按**约定 24**——**每次** commit 前先跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 读 JSON；退出码 3/4 = 本轮结束前有义务未落地（约定 22 台账积压 → 派台账收口子 Agent；CICD 推送欠账 → 补监听），**不是禁止 commit**（判定字段与处置单一信源 = 约定 24，本命令不复述）。

> ★ **推送分类与监听（约定 31.5，独立跑本命令时同样适用）**：本命令 push 前先调用 `python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --version "$VERSION" [--build "$BUILD"]` 并写入当前 build（⛔ 别写成 `classify_commit_change.py`：那个只出分类、无 `--version`/`--build`、不落盘）。无正式代码变更且分类无错误时，仍校验 push 成功并记录 `cicd_skipped=true`，不触发/监听远端 CICD、不跑就绪探针；正式代码变更或分类错误时，若项目已接入 CICD（`memory/aidp-config.yaml` 的 `cicd.provider` ≠ `none` 且 `cicd.pipelines` 已配，默认 GitHub Actions），则经 `python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode watch --commit <sha> --env <env>` 监听本次推送触发的运行至终态、失败自动重试（`cicd_watch.py --mode retry`）≤3 次并通过就绪探针。分类结果缺失、调用失败或无法落盘时按正式代码路径 fail-closed。规则单一信源 = 约定 31.5 +「推送分类与监听不变式」（`{{AIDP_HOME}}/flows/sprint-autopilot/invariants.md`）。

---

### Phase 2-4：自动串联后续（分支 A / B 共用 —— 串联规则单一信源）

**默认行为**（分支 B，或分支 A 不带 `skip-test`）：开发完成后自动执行：

```
# ★ 本串联块同轮跑 test → bugfix → close，而约定 22 的收口点**不含 `/sprint-close`**：
#   不当场级联，本 Sprint 的 `/sprint-test` 就拿不到本轮新增的 L4 用例（要等次日首次提交才成文）。
#   ⛔ 故走到这里时**本命令自身必须已带 `--cascade-now`**（`/sprint-full` 已硬编码传它，两边同款）；
#   分支 B 或不带 skip-test 的分支 A 进入本块前自动置上，别留给用户记得加。
# ⛔ 本命令带 --unattended 时，下面三条【必须逐条透传】——不传则下游各自弹交互门，
#   无人值守链在此挂死（/sprint-close 的"确认验收"更是只有该 flag 才走机械推导）。
#   三条缺一不可（`/sprint-full` 同款，两边须同步）。
1. /sprint-test [--unattended]                    # 测试（含 code-verification-loop）

2. 如发现 bug:
   循环：
     /sprint-bugfix sprint-{NNN} [--unattended]   # 修复
     /sprint-test [--unattended]                   # 回归
   直到全部 Fixed/Verified 或循环 5 次

3. /sprint-close {NNN} [--unattended]             # 关闭归档
```

**跳过串联**：参数含 `skip-test` → 只执行开发，后续步骤由用户手动触发。

---

## 输出

### 分支 A（只开发：参数含 skip-test；被编排器调用时由 `/sprint-full`·`/sprint-batch` 透传 skip-test 落入本分支，test/bugfix/close 归编排器负责）

```
✅ /sprint-dev 完成（Sprint-{NNN} 开发阶段）

开发范围：{后端/前端/全部}

后端（TDD 模式）：
- {列出实现的模块和接口}
- 单元测试：{N} 个通过
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
/sprint-dev           # 开发后【自动串联】test→bugfix→close（默认行为）
# 仅开发、不串联 → 必须显式带 skip-test
/sprint-dev 001 skip-test

# 场景 3：★ 独立使用自动累进
/sprint-dev "新增用户导出功能"
# 自动：累进 Sprint-006 → 开发 → 测试 → 修复 → 关闭

# 场景 4：只想开发不想自动测试
/sprint-dev "增加菜单缓存" skip-test

# 场景 5：只开发后端部分
/sprint-dev "重写权限模块" backend
```
