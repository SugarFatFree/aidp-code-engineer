# /version — 版本管理命令（★）

你正在执行 `/version` 命令。根据版本号的当前状态自动执行「规划」或「发布」。

参数：$ARGUMENTS
- 版本号（**必须**，格式 `V{major}.{minor}.{patch}`，例 `V0.1.0`）
- 第二参数（**可选**，自然语言）：用户可以传两类内容——
  - **规范里程碑名**（如 `"M1 MVP"` / `"M2：用户中心"`）→ 命令端按 `^M\d+` 正则判定为已规范，直接采用
  - **版本描述自由文本**（如 `"新增用户登录和权限管理"` / `"修复支付链路若干 bug"`）→ Step 2.1.5 把它作为最高优先级的派生依据，生成 `M{N}：<≤12 字摘要>` 格式的里程碑名

格式示例：
- `/version V0.1.0` — 规划新版本（里程碑由 Step 2.1.5 从研发需求/PRD 自动派生）或发布该版本（取决于 Step 1 模式决议）
- `/version V0.1.0 "新增用户登录与权限管理"` — 规划新版本（用户给了**版本描述**，命令端派生 `M{N}：<摘要>`）
- `/version V0.1.0 "M1 MVP"` — 规划新版本（用户给了**规范里程碑名**，直接采用）

## 可选 flag 清单

| flag | 用途 | 行为锚点 |
|------|------|---------|
| `--release` | 强制走版本发布流程（情况 B-3），即使输入未变 | [Step 1 模式决议](#step-1判断执行模式)（情况 B-3）+ [版本发布流程（情况 B-3）](#版本发布流程情况-b-3) |
| `--skip-audit` | 跳过 Step 2.4.7 版本规划产物全量审计（**唯一允许跳过审计的条件**） | [Step 2.4.7](../flows/version/planning-7.md) |
| `--no-tag` | 准发布模式：提交 + 推送 commit 但**不打 tag、不建版本分支**（供 `/sprint-autopilot` 调用；tag 与大写版本分支 `V{version}` 都留正式发布） | [Step 3.4 `--no-tag` 准发布模式](../flows/version/release-7.md) |
| `--unattended` | 无人值守上下文标记（`/sprint-autopilot` `/loop` 透传）：① Step 0 根目录产品输入归位**不弹 `AskUserQuestion`**，按默认动作直接移动并留痕；② Step 2.4.7 版本规划产物审计 `block` 时**不弹 `AskUserQuestion`**，自动修复 3 轮仍不过则返回 `audit-block` 失败信号交 autopilot 熔断；③ 发布路径白名单门按其既定无人值守分支处理（与 `--no-tag` 同属非交互 / 后台触发场景） | [Step 0](#step-0根目录产品输入归位检测prd--原型版本规划前置) + [Step 2.4.7](../flows/version/planning-7.md) |
| `--finalize-docs` | **发布期文档整理补跑模式（短路）**：只跑 Step **3.3.9.5**（收口开发期变更台账，⛔ 必须**先于** 3.3.10）+ 3.3.7（部署产物整理）+ 3.3.10（版本规划文档收敛）+ 3.3.11（全量详细设计重算）+ 3.3.13（代码内版本标识对齐复核），**跳过发布主流程 / 不打 tag**。用于此前发布时这几步因流程脆弱触发失败兜底被跳过后，**一键事后补齐**——读 `docs/audit/{version}/发布欠账.md` 定位欠账逐条补、补齐即勾销 | [`--finalize-docs` 补跑短路](#--finalize-docs-补跑短路发布期文档整理) |
| `--full-rebuild` | **强制全量重建 Step 3.3.11 全量详细设计**：跳过「变更范围增量」、对全部专题从零重算（等价旧覆盖式重算）。默认发布走**变更范围增量**（只重算本次动过的专题、其余前滚，见 `release-6.md`）；本 flag 用于**手动清增量漂移**或**首次建立全量基线**。可与正常发布 / `--finalize-docs` 叠加 | Step 3.3.11（`release-6.md` 变更范围增量重算） |
| `--rebuild-baseline` | **双轨部署基线补跑模式（短路，约定 37）**：只跑 Step 3.3.7.9（产出 `sql/全量/` + `配置文件/全量/` 全量轨 + 增量轨发布期校准 + `release_baseline_check.py` 机器门），**跳过发布主流程 / 不打 tag**。用于本步因**真实库或配置中心不可达**被跳过后事后补齐——全量基线依赖线上环境可达，发布当时未必满足；读 `docs/audit/{version}/发布欠账.md` 定位欠账，补齐即勾销 | Step 3.3.7.9（`release-4.md` D 部分双轨部署基线） |
| `--scale=S\|M\|L` | **显式指定需求规模档位**，覆盖 Step 2.4.1.5 自动判定（S 小/M 中/L 全套；控设计册数·用例数·task 是否分册，小需求不走大流程）。不带则据 REQ 数/页面数/是否建表自动判档 | Step 2.4.1.5（`planning-3.md` 需求规模档位判定门） |

## 前置流程

**VCS 能力门（先于补跑短路和 Step 1）**：调用 `{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 取得 `vcs_mode=git|none`，`developer_identity(Path.cwd())` 取得 `{user}`。`git` 保持原规划/发布流程；`none` 仍允许本地版本规划；`--finalize-docs` 只有能从可信本地发布台账核实未发布状态才允许本地整理，否则在任何文档改写前 fail-closed 并报告「无法核实已发布状态」，不得拿缺 tag 当未发布。其中 Git-only tag 核验、commit/push 均记 `unsupported:vcs-disabled`（非 passed），不得据此认定已发布。任何正式发布路径（含 `--release`、普通情况 B-3、`--no-tag` 准发布）的 tag/分支/push 在 `vcs_mode=none` 下一律 fail-closed：发布操作开始前退出，明确报告 `unsupported:vcs-disabled`，不写 `internal_released_at` 或发布完成标记、不得宣布已发布。`--rebuild-baseline` 在无 Git 时只可处理不依赖 tag 的未发布本地基线；无法确认是否已发布则停止，不改写可能已发布的产物。此门不改变 Git 模式的发布语义。

1. **{version}** ← 命令参数（显式提供，不从项目记忆文件读取）
2. **{user}** ← `git config user.name`
3. 校验 {version} 格式；不合法时按 `docs/init/06_版本与用户目录约定.md` 第 6 节话术重问。

## `--rebuild-baseline` 补跑短路（双轨部署基线，约定 37）

> 用于 Step 3.3.7.9 因**真实库或配置中心不可达**被跳过后事后补齐——全量基线依赖线上环境可达，
> 发布当时未必满足。当本次调用带 `--rebuild-baseline` 时**在 Step 1 模式决议之前短路**：

- **前置**：`{version}` 必须**已存在版本规划产物**（`docs/design/detail/{version}/` 或 `docs/plans/{version}/` 存在）；否则报错并退出。
- **★ 已发布版本保护**（`git tag -l "v${VERSION#V}"` 或远端 `git ls-remote --tags origin` 命中 = 已打 tag）：全量基线「随 tag 冻结」，补跑即改写已发布产物 → 走「改写已发布版本授权门」（发布路径白名单第 4 处，见 `release-1.md`）：**交互式**二选一（① 授权改写 ② 中止，改为新补丁版本补齐）；**无人值守拒绝执行**（登记 `release_debt.py add --step 3.3.7.9 --title "补跑被拒：版本已打 tag"` 后退出）。获授权后**采集基于 tag 对应代码**（`git worktree add <临时目录> v${VERSION#V}`，在该工作树内读 ORM 声明与配置消费面，⛔ 不用 HEAD 代码），产物写回主工作区。
- **只跑一步**：**Step 3.3.7.9**（D 部分双轨部署基线 —— 产 `sql/全量/` + `配置文件/全量/` 全量轨
  + 增量轨发布期校准 + `release_baseline_check.py` 12 项机器门）。**跳过其余全部**
  （Step 0 ~ 3.3.7.8、3.3.8 ~ 3.3.13、3.4.x 发布提交/打 tag 一律不执行）。
- **★ 欠账驱动**：开始先读 `docs/audit/{version}/发布欠账.md`（若存在）定位本步被跳过的原因；
  补齐成功即 `release_debt.py resolve --version {version} --step 3.3.7.9` 勾销。
- **环境确认门**：Step 3.3.7.9 的「全量基线从哪个环境导出」确认门**照常弹**（属发布路径允许交互的
  四处结构化门之一，见 `release-1.md`）；`--unattended` 下按其既定无人值守分支处理。
- **提交**：自行 `git add docs/deployment/{version}/` + commit（消息 `docs({version}): rebuild-baseline 补齐双轨部署基线`）
  + push 本分支，**绝不打 tag、不建/不推版本分支**。⛔ **push 前必挂推送分类**（约定 31.5「推送 ≠ 交付完成」——⛔ 不是只有 autopilot 的 push 点要落实）：提交前存 `BASE_REF`，**`git push` 之【前】**跑 `python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --version "$VERSION" --standalone --base-ref "$BASE_REF"`；**分类缺失 / 命令失败 / `classification_error=true` 一律按正式代码走 CICD 监听（fail-closed）**，纯文档变更才记 `cicd_skipped=true` 并跳过监听。骨架照抄 `release-7.md` **Step 3.4.3**（自动推送 commit + tag + 版本分支，分类在 `git push` 之前）——⛔ 不是 Step 3.4.4，那是失败处置（rebase / 强推 / tag 保护降级），照它抄只会抄到失败分支、抄不到分类与监听。
  > 🔗 约定 24 提交前门禁同其余 commit 路径（`git commit` 前跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet`；单一信源 = 约定 24）。
- **完成播报**：打印本次产出的全量轨文件数 + 机器门 12 项结果 + 台账剩余未决项。

## `--finalize-docs` 补跑短路（发布期文档整理）

> 用于**发布时 Step 3.3.7 / 3.3.10 / 3.3.11 / 3.3.13 因流程脆弱触发失败兜底被跳过**后，一键事后补齐——不必重跑整个 `/version`、不重新打 tag。当本次调用带 `--finalize-docs` 时**在 Step 1 模式决议之前短路**：

- **前置**：{version} 必须**已存在版本规划产物**（`docs/design/detail/{version}/` 或 `docs/plans/{version}/` 存在）；否则报错「{version} 尚未规划，请先 `/version {version}` 规划/发布」并退出。
- **★ 已发布版本保护**：`vcs_mode=none` 时，在读取欠账或改写任何文件之前先核对项目记忆中的版本状态与 baseline `internal_released_at`、本地发布台账；任一显示已发布或互相矛盾、缺失而无法核实已发布状态 → fail-closed 退出并报告 `unsupported:vcs-disabled`，不执行五步、不勾销欠账（不能用无 tag 推断未发布）。仅有明确一致的「未发布」本地状态才可做本地文档整理，Git 提交/推送记 skipped。`vcs_mode=git` 时已打 tag 同 `--rebuild-baseline` 的「已发布版本保护」——交互式先过改写授权门、无人值守拒绝执行并登记欠账；获授权后各步以 tag 对应代码为事实源（`git worktree add` 取 tag 工作树）。
- **只跑五步、按序**：① **Step 3.3.9.5**（收口开发期变更台账 —— ⛔ 必须先于 3.3.10，否则台账内容赶不上主文档合并）② **Step 3.3.7**（部署产物整理完善——A/B/C 三部分，**B/C 独立强制执行**，见其解耦说明）③ **Step 3.3.10**（版本规划文档收敛——历史归一 + 取代链消解 + 族级/项级粒度合并）④ **Step 3.3.11**（全量详细设计重算——**默认变更范围增量**〔只重算动过的专题、其余前滚，见 `release-6.md`〕，可叠 `--full-rebuild` 强制全量；带 `--no-tag` 时同正式发布口径跳过，纯 `--finalize-docs` 视为正式补跑、执行）⑤ **Step 3.3.13**（代码内版本标识对齐复核——补跑场景下**只复核 + 更新台账状态**，不自动改代码〔改代码须回正式发布的交互式确认门〕）。**跳过**其余全部（Step 0 ~ 3.3.5、Step 3.3.8/3.3.9/3.3.12bis、Step 3.4.x 发布提交/打 tag）。
- **★ 欠账驱动**：开始先读 `docs/audit/{version}/发布欠账.md`（若存在）——**优先补齐其中登记的跳过项**（按「精确定位」逐条处理），补齐成功即 `release_debt.py resolve` 勾销对应步骤；台账不存在则对四步全量重跑一遍（幂等：已整理干净的族/产物 no-op、不重复动）。
- **提交**：本短路**自行 `git add` 四步产物 + commit**（消息 `docs({version}): finalize-docs 补齐发布期整理`）+ `git push` 本分支，但**绝不打 tag、不推送 tag、不建/不推版本分支**（tag 与大写版本分支都仍由正式 `/version {version}` 管控）。⛔ **push 前必挂推送分类**（约定 31.5「推送 ≠ 交付完成」——⛔ 不是只有 autopilot 的 push 点要落实）：提交前存 `BASE_REF`，**`git push` 之【前】**跑 `python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --version "$VERSION" --standalone --base-ref "$BASE_REF"`；**分类缺失 / 命令失败 / `classification_error=true` 一律按正式代码走 CICD 监听（fail-closed）**，纯文档变更才记 `cicd_skipped=true` 并跳过监听。骨架照抄 `release-7.md` **Step 3.4.3**（自动推送 commit + tag + 版本分支，分类在 `git push` 之前）——⛔ 不是 Step 3.4.4，那是失败处置（rebase / 强推 / tag 保护降级），照它抄只会抄到失败分支、抄不到分类与监听。
  > 🔗 **约定 24 提交前门禁（本命令所有 commit 路径通用，不复述细节）**：`git commit` 前先跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 读 JSON；退出码 3/4 = 本轮结束前有义务未落地（约定 22 台账积压 → 派台账收口子 Agent；CICD 推送欠账 → 补监听），不是禁止 commit；判定字段与处置**单一信源 = 约定 24**。
- **无人值守**：`--finalize-docs --unattended` 下五步失败兜底走无人值守分支（WARN + 台账登记、不弹窗）。
- **完成播报**：打印本次补齐结果（收敛 N 族 / 全量重算成功与否 / 部署产物完善项）+ 台账剩余未决项（仍需人工处理的「待人工合并清单」）。

## 发布期整理欠账台账（`docs/audit/{version}/发布欠账.md`）

> **★ 失败兜底可追溯铁律（消除"静默跳过、长期欠账"）**：Step 3.3.7（部署整理）/ **3.3.7.9（双轨部署基线）** / **3.3.9.5（台账收口）** / 3.3.10（文档收敛）/ 3.3.11（全量重算）/ **3.3.12bis（零残留断言总闸）** / 3.3.13（版本标识对齐）的**任一失败兜底（WARN 跳过）都必须登记到** `docs/audit/{version}/发布欠账.md`——**绝不只在终端 WARN 一句就过**。发布报告 Step 3.6 引用本台账，`--finalize-docs` 读本台账驱动补跑。

**登记时机**：上述任一步骤的**某项 / 某族**因守恒失败 / 语义无法机械收敛 / 联动删除引用不一致 / 解析异常 / 编号冲突无法自动重编 / **代码内自报版本与发布版本不一致（无人值守下不自动改）**而被跳过时登记一条。

**读写唯一入口 = `python3 {{AIDP_HOME}}/scripts/release_debt.py`**（⛔ 不手写 `echo >>`；条目格式、幂等、状态字段均由脚本保证）：

| 动作 | 命令 |
|---|---|
| 登记（同一 step+title 未决时只刷新时间戳） | `release_debt.py add --version {version} --step <步骤> --title "<跳过项>" --note "<原因>" --locate "<精确定位>" --impact "<影响>" --redo "<补跑命令>"` |
| 勾销（补跑成功后） | `release_debt.py resolve --version {version} --step <步骤> [--title "<跳过项>"]` |
| 数未决（Step 3.6 顶部欠账块 / 补跑短路开场） | `release_debt.py list --version {version} --open --json` |
| 终态落账门（Step 3.4.1 提交前，`release-7.md`） | `release_debt.py gate --version {version} [--no-tag] --register-missing` —— 关键产物（全量部署基线 / 全量详细设计）缺失且台账无对应条目时当场补登记，堵「跳过了却没留账」 |

**未决条目在发布报告顶部醒目提示**「⚠️ 本版本有 N 项发布期整理欠账未决，见 `docs/audit/{version}/发布欠账.md`，可 `/version {version} --finalize-docs` 补齐」。**无欠账则不生成台账文件**（避免噪音）。

## 两类跳过铁律（全命令通用）

> ### ★ item 8：两类跳过铁律（"留痕跳过"是低阻力路径，绝不让 AI 优先走）
> 任何"本应做却没做"的动作，落跳过前**先分类**——分类决定合规出口，**严禁一律"留个痕就跳过"**（留痕对 AI 是低阻力路径 + autopilot「绝不停下来问」铁律进一步压低询问倾向，二者叠加会把"用户本可决策的事"静默跳掉）：
> - **第一类·技术性不可用**（外部服务不可达 / 平台接口返回失败 / DB 直连不通 / CICD 提供方 CLI·凭据不可用等，**当前客观无法完成、无用户可选替代**）→ **留痕跳过合规**：终端 WARN + 报告写原因 + 补跑命令，继续主流程。
> - **第二类·存在用户可决策替代**（换部署方式 / 暂停等待部署完再测 / 补建缺失配置 等，**用户一句话就能定**）→ **不得自行留痕跳过**：**交互式**必须 `AskUserQuestion` 把替代项列给用户选（补建 / 换方式 / 跳过+写清理由）；**无人值守**（`--no-tag`/`--unattended`）→ 记 baseline `versions.{V}.builds[current_build].decidable_skips[]`（结构化一条，如 `post-release-accrue-defaulted-patch`）**转 needs_human 上浮**（ceremony-gate 3f 收尾显式列出、要求人工确认），**不静默记进 `activeContext.md` 了事**。
> - **判定速记**：问一句"用户在场能不能一句话给出别的做法？" 能 → 第二类（问 / 上浮）；不能（纯客观卡住）→ 第一类（留痕跳过）。拿不准按第二类处理（宁可上浮不可静默）。

## Step 0 前置组

### Step 0：根目录产品输入归位检测（PRD / 原型，版本规划前置）

> 在 Step 2.0 扫描版本输入（`docs/requirements/{version}/产品提供/` + `docs/prototype/{version}/`）之前，先检测产品是否把 **PRD 文档 / 原型代码目录** 直接放在**项目根目录**（尚未归入 AIDP 目录）；检测到则**经用户确认后移动**到本版本对应目录，让后续步骤直接读到。与 `/aidp-code-engineer` init Step 1.1.5 同源逻辑（同套检测/分流/移动规则）。

```bash
VER="{version}"   # 命令参数，已知
# PRD 候选：根目录文件，名字含 prd/需求/产品/requirement + 文档扩展名（排除 AIDP 自身文档）
PRD_HITS=$(find . -maxdepth 1 -type f \
  \( -iname "*prd*" -o -iname "*需求*" -o -iname "*产品*" -o -iname "*requirement*" \) \
  \( -iname "*.md" -o -iname "*.markdown" -o -iname "*.docx" -o -iname "*.doc" -o -iname "*.pdf" \) \
  2>/dev/null | sed 's|^\./||' | grep -viE "^(README|版本变更历史|版本更新日志)")
# 原型目录候选：根目录目录，名字含 prototype/原型/mockup/高保真/ui-prototype（排除 AIDP/标准目录）
PROTO_HITS=$(find . -maxdepth 1 -type d \
  \( -iname "*prototype*" -o -iname "*原型*" -o -iname "mockup*" -o -iname "*高保真*" -o -iname "ui-prototype*" \) \
  2>/dev/null | sed 's|^\./||' | grep -vE "^(docs|code|node_modules|env|memory|\.)")
```

- `PRD_HITS` 与 `PROTO_HITS` 均空 → **跳过本步**，直接进 Step 1。
- 有命中 + **交互式** → 用 `AskUserQuestion` 列出命中清单 + 目标路径（PRD→`docs/requirements/{version}/产品提供/`；原型→`docs/prototype/{version}/code/` 或 `mockup/`），让用户选 **移动 / 复制 / 跳过**（默认**移动**；命中清单逐项可剔除误判）。
- 有命中 + **无人值守**（`--unattended` / `--no-tag` / `LOOP_UNATTENDED`）→ ⛔ **绝不弹 `AskUserQuestion`**：按默认动作**直接移动**、打印归位清单、并在 Step 2.8 报告「产品输入归位」段逐条留痕（含误判可回退的原路径）。**Why**：产品把 PRD/原型丢在仓库根正是本步存在的理由、也是 autopilot 场景的典型动作；这里裸露一个问询会让 `/loop 10m /sprint-autopilot --unattended` 的**首个 tick** 就停在无人可答处——而本步排在 Step 1 模式决议之前，规划/发布两条路径必经。
- 用户确认 **移动** 后执行（`git mv` 优先保历史、失败回退 `mv`；目标已存在则跳过不覆盖；选「复制」则把 `git mv ... || mv` 换 `cp -r`、根目录保留原件）：

```bash
mkdir -p "docs/requirements/${VER}/产品提供" "docs/prototype/${VER}/code" "docs/prototype/${VER}/mockup"
# PRD → 产品提供/
echo "$PRD_HITS" | while IFS= read -r f; do
  [ -z "$f" ] && continue
  dest="docs/requirements/${VER}/产品提供/$(basename "$f")"
  [ -e "$dest" ] && { echo "⚠️ 目标已存在，跳过不覆盖：$dest"; continue; }
  git mv "$f" "$dest" 2>/dev/null || mv "$f" "$dest"
done
# 原型目录 → 按多数扩展名分流 code/（前端代码）或 mockup/（图片/PDF/设计源），整目录搬迁保留子结构
echo "$PROTO_HITS" | while IFS= read -r d; do
  [ -z "$d" ] && continue
  code_n=$(find "$d" -type f \( -iname "*.html" -o -iname "*.vue" -o -iname "*.jsx" -o -iname "*.tsx" -o -iname "*.js" -o -iname "*.ts" -o -iname "*.css" -o -iname "*.wxml" -o -iname "*.wxss" \) 2>/dev/null | wc -l)
  img_n=$(find "$d" -type f \( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.gif" -o -iname "*.svg" -o -iname "*.pdf" -o -iname "*.fig" -o -iname "*.sketch" -o -iname "*.xd" \) 2>/dev/null | wc -l)
  [ "$img_n" -gt "$code_n" ] && sub=mockup || sub=code
  dest="docs/prototype/${VER}/${sub}/$(basename "$d")"
  [ -e "$dest" ] && { echo "⚠️ 目标已存在，跳过不覆盖：$dest"; continue; }
  git mv "$d" "$dest" 2>/dev/null || mv "$d" "$dest"
  [ "$sub" = code ] && [ "$img_n" -gt 0 ] && echo "ℹ️ $dest 含 $img_n 个图片/PDF，如属高保真设计稿可手动移到 docs/prototype/${VER}/mockup/"
done
```

- 移动后随版本规划产物一并 commit（或单独 `chore(归位): 根目录 PRD/原型 → AIDP {version} 目录`）。
- **不自动判定的兜底**：根目录若有名字未命中、但含大量 `.html/.vue/.jsx` 的目录（疑似 vibe coding 导出原型），**只在确认问询里列出供用户人工勾选**，不自动归类。

> 📎 **本文档章节体系过渡说明**：`Step N` 连续编号**只覆盖到 Step 1 为止**（Step 0 前置组 → Step 1 判断执行模式，线性必经）。Step 1 决议出分支后，本文档改按**分支流程章节**组织——「版本规划流程（情况 A / B-2）」「版本发布流程（情况 B-3）」「情况 C：版本已发布」；各分支内部的 `Step 2.x` / `Step 3.x` 编号在其**外置分片**（`{{AIDP_HOME}}/flows/version/planning-N.md` / `release-N.md`）内延续，本文档只保留骨架索引表。下方「角色：PM Agent」是贯穿全流程的角色声明，不占 Step 序号。

## 角色：PM Agent

读取 `{{AIDP_HOME}}/agents/pm.md` 获取角色定义。

## Step 1：判断执行模式

读取以下文件判断 {version} 的当前状态：
1. `memory/{version}/{user}/progress.md` 的「版本历史」表格（若存在）
2. 项目记忆文件（`agent_env.py memory-file` 取路径）的「当前状态」区域
3. `memory/{version}/.aidp-inputs-snapshot.json`（上次 /version 运行时记录的**全部输入文件**——PRD 与原型——的 sha256 快照，详见 Step 2.0）
4. **当前输入实测**：
   - PRD：`docs/requirements/{version}/产品提供/**/*.md`
   - 原型：`docs/prototype/{version}/code/**/*`（HTML/Vue/JSX/CSS 等）+ `docs/prototype/{version}/mockup/**/*`（PNG/JPG/PDF/Figma 导出等）

模式决议：

- **情况 A：目录与历史均不存在** → 执行**版本规划**流程（**fresh 模式** — 全量生成 6 类主文档）
- **情况 B-1：版本已存在 + 状态「🚧 开发中」 + 输入全部未变**（PRD + 原型 + **代码结构性文件** sha256 三类都与快照全等）→ 提示"输入文档与代码结构均未变化，已生成的设计/计划/用例均为最新；如需重生成请删 `.aidp-inputs-snapshot.json`"并退出
- **情况 B-2：版本已存在 + 状态「🚧 开发中」 + PRD 或原型或代码结构已变**（**任一来源 sha256 不等**，或快照不存在但当前已有输入文件 + 至少一份主文档存在）→ 执行**版本规划增量流程（补充模式）**：产出 `NN_<业务主题>.md` 系列增量文档（文件名不带"补充"字眼），并在各目录 `00_索引.md` 登记（类型=补充 + 生成时间）；**绝不覆盖已有主文档**
  - 触发源含**代码变更**（无 PRD/原型变更但 sprint-dev 累进产生的新接口/表/页面）→ 走 sprint-design Step 0.3 四象限「③ 代码超前-补写」路径，dev-logic-architect 把代码现状反向追平为设计补充文档
- **状态「🟡 已准发布（未打 tag）」**（`--no-tag` 准发布写入）：在 A / B-1 / B-2 / B-3 判定中**与「🚧 开发中」等同**，⛔ 不算已发布、不进情况 C；正式 `/version {version}` 即按 B-3 首次打 tag
- **情况 B-3：版本已存在 + 状态「🚧 开发中」 + 用户希望按发布流程跑**（通过显式 `--release` 参数或输入未变 + 用户在交互中选择"发布版本"）→ 执行**版本发布**流程
- **情况 C：版本已存在且状态为「✅ 已发布」** → **重新发布（re-release）**：⛔ **先过改写授权门、再动任何文件**（白名单第 4 处前移到本入口：3.3.x 会重写已发布文档、3.4.1 提交、3.4.3 推送，授权放在其后等于先改后问）——**交互式**二选一（① 授权重新发布 → `baseline_edit.py --version {version} set release_force_authorized 1` 后走 B-3；② 中止，改用新补丁号）；**无人值守**拒绝重新发布、直接退出（不改写任何已发布产物）。并置 `REPUBLISH=1`——自动关闭所有未关闭 Sprint、重跑发布产物、**强制重打 tag（`git tag -f`）+ 强制重建版本分支（`git branch -f`）** 指向本次新发布提交 + 强制推送（`git push -f`）；终端 WARN 记「重新发布 {version}：tag/分支已移动到新提交」。（若只想补充设计而非重新发布 → 另开版本号 `/version V?.?.?`。）

判定优先级：A → B-1（无操作）→ B-2（补充）→ B-3（发布）→ C（重新发布）。

> 📌 **模式决议只看 `{version}` 自身状态，不看其它版本是否已发布（中间过渡版本合法）**：用户在当前版本**尚未发布**时直接跑 `/version {下一版本号}` 开始下一版规划，是**合法操作**——这本身即声明"当前版本属中间过渡版本、不需要正式发布"。**照常按上表决议并规划，绝不询问"要不要先发布上一版"、不阻塞、不自行补发布、不记欠账**（约定 2 细则「中间过渡版本」）。规划期需要"上一版本"时取**上一迭代版本**（含未发布的过渡版本），口径见 Step 2.4.7；发布期的对外对比基准仍取上一**已发布**版本。

**分支 → 流程章节对照**（消除读者推断）：

| 决议分支 | 进入流程 | 本文档章节 |
|---------|---------|-----------|
| 情况 A | 版本规划（fresh 全量） | [版本规划流程（情况 A 全量 / B-2 补充）](#版本规划流程情况-a-全量--b-2-补充) |
| 情况 B-1 | 无操作退出 | 上文 Step 1（提示"输入未变"后退出，无后续 Step） |
| 情况 B-2 | 版本规划增量（补充模式） | [版本规划流程（情况 A 全量 / B-2 补充）](#版本规划流程情况-a-全量--b-2-补充) 的补充模式分支 |
| 情况 B-3 | 版本发布 | [版本发布流程（情况 B-3）](#版本发布流程情况-b-3) |
| 情况 C | 重新发布（re-release；入口先过改写授权门，未授权即退出） | [情况 C：版本已发布](#情况-c版本已发布) |

**补充模式提示用户**：进入 B-2 时，命令端必须先向用户播报：
- 检测到 PRD 变更的具体文件清单（含 sha256 前 8 位差异）
- 检测到原型变更的具体文件清单（含 sha256 前 8 位差异 + 区分代码原型 / 高保真）
- 即将进入"补充模式"，将产出 `NN_<业务主题>.md` 补充文档
- 不会覆盖任何已存在的主文档
- 用户可输入 "abort" 中止；任何其他输入即视为确认

---

## 版本规划流程（情况 A 全量 / B-2 补充）

> ⛔⛔ **详细步骤已外置为 8 个分片、进入版本规划流程的【第一动作】= 按需加载**：Step 2.0–2.8 的完整步骤外置到 **`{{AIDP_HOME}}/flows/version/planning-1.md` … `planning-8.md`**（每片 ≤20KB）。**按 Step 进度依次 `Read` 对应分片、逐项执行**——下方骨架表的「分片」列给出每组 Step 落在哪一片；**权威判定一律以对应分片正文为准，绝不凭骨架或记忆略过任一子步骤/硬门**。进入本流程先 `Read planning-1.md` 起步，随 Step 推进再 `Read` 后续分片。
>
> ⛔ **关键硬门（详见 `planning-7.md`）**：Step 2.4.7「版本规划产物全量审计」是**强制执行铁律**——独立子 Agent 隔离上下文跑 8 项审计（含 Critical 硬门 C-4/C-5/F/G），唯一合法跳过 = `--skip-audit`；补充模式（B-2）绝不覆盖主文档、只产 `NN_<业务主题>.md` 增量并登记 `00_索引.md`。

**版本规划流程子步骤骨架 + 分片索引（详见对应 `planning-N.md`）**：

| 子步骤 | 作用（一句话） | 分片 |
|---|---|---|
| **2.0** | ★ 输入快照管理（PRD/原型 sha256，检测中途改动触发补充模式） | `planning-1.md` |
| **2.1** | 校验参数 + 第二参数分流 | `planning-1.md` |
| **2.1.5** | ★ 自动派生里程碑名称（AUTO_NO_HINT / AUTO_FROM_HINT） | `planning-1.md` |
| **2.2** | 读取上下文 | `planning-2.md` |
| **2.3** | 创建版本目录骨架（含 requirements 标准子目录 + 散落 PRD 自动归位） | `planning-2.md` |
| **2.4** | ★ 协调调用四个文档生成步骤（requirements/design/plan/selftest） | `planning-2.md` |
| **2.4.0** | 生成输入变更摘要（仅补充模式 B-2） | `planning-2.md` |
| **2.4.0.8** | ★ 上游契约待确认点前置提取（fresh / 补充**两种模式都执行**；非阻塞）| `planning-2.md` |
| **2.4.1–2.4.3.5** | 调 /sprint-requirements → /sprint-design → /sprint-plan → /sprint-selftest | `planning-3.md` |
| **2.4.4** | ★ 产物归一 + `00_索引.md` 维护（约定 15） | `planning-4.md` |
| **2.4.5 / 2.4.5.5 / 2.4.5.6** | 串联说明 + 索引补充登记 + 结论取代传播（补充模式） | `planning-5.md` |
| **2.4.6** | ★ 关联文档交叉引用校验 | `planning-6.md` |
| **2.4.7** | ⛔ ★ 版本规划产物全量审计（独立子 Agent；强制铁律；唯一跳过 `--skip-audit`） | `planning-7.md` |
| **2.5 / 2.6** | 初始化 progress.md / activeContext.md | `planning-8.md` |
| **2.7 / 2.7.3 / 2.7.5** | 更新项目记忆文件当前版本 / ★ 同步代码内本应用版本号（`pom.xml`·`package.json`·`Dockerfile` 等构建描述符随版本号 bump 自动改齐）/ 更新 PRD 快照 | `planning-8.md` |
| **2.7.4** | ★ 收口**上一版本**遗留的开发期变更台账（约定 22 攒批级联 · 收口点 2）| `planning-8.md` |
| **2.8** | 输出规划报告 | `planning-8.md` |

> 收口：Step 2.8 完成 → 版本规划结束（回主流程）。**执行前务必已按 Step 进度 Read 对应 `planning-N.md` 并逐项完成。**

---

## 版本发布流程（情况 B-3）

> 对应 Step 1 模式决议的 **B-3 分支**（版本已存在 + 状态「🚧 开发中」 + 用户经 `--release` 或交互选择"发布版本"）。B-1 无操作退出 / B-2 走补充模式（上方版本规划流程）/ B-3 才进入本节正式发布。

> ⛔⛔ **详细步骤已外置为 9 个分片、进入版本发布流程的【第一动作】= 按需加载**：交互式发布决策纪律 + tag 风格识别约定 + Step 3.1–3.6 的完整步骤外置到 **`{{AIDP_HOME}}/flows/version/release-1.md` … `release-7.md` / `release-7b.md` / `release-7c.md`**（每片 ≤20KB；Step 3.5/3.6 切分到 `release-7b.md`、Step 3.4.4 失败处置切分到 `release-7c.md`）。**按 Step 进度依次 `Read` 对应分片、逐项执行**——下方骨架表的「分片」列给出每组 Step 落在哪一片；**权威判定一律以对应分片正文为准，绝不凭骨架或记忆略过任一子步骤/硬门**。进入本流程先 `Read release-1.md` 起步（决策纪律 + tag 约定 + 前置检查），随 Step 推进再 `Read` 后续分片。
>
> ⛔ **关键硬门（详见 `release-1.md`）**：**交互式发布 = 全量执行**——发布一经启动即全量跑完 Step 3.1 → 3.6，中途绝不弹「是否继续 / 是否发布 / 要不要先验证」；允许交互的结构化门共**四处**（3.1 P0 强制发布确认 / 3.3.7.9 全量基线环境 / 3.3.13 版本标识**复检仍不一致**那一格 / **3.4.2.2 移动已发布 tag 的授权门**，白名单单一信源见 `release-1.md`）；⛔ 每次 `AskUserQuestion` 前须先指名它是白名单哪一项，指不出来即违规（前置自检见 `release-1.md`）

**版本发布流程子步骤骨架 + 分片索引（详见对应 `release-N.md`）**：

| 子步骤 | 作用（一句话） | 分片 |
|---|---|---|
| **⛔ 交互式发布 = 全量执行** | 决策纪律铁律 + 允许交互的穷举白名单 + 默认处置优先级 | `release-1.md` |
| **tag 风格识别约定** | 三种 tag 命名风格全覆盖取最新（供 3.3.5/3.4.2/2.4.7 引用） | `release-1.md` |
| **3.1** | 前置条件检查（未关闭 Sprint 自动关闭；P0 强制发布确认门） | `release-1.md` |
| **3.2 / 3.3 / 3.3.5** | 收集版本信息 / 更新版本历史表格 / 生成版本更新日志.md | `release-2.md` |
| **3.3.7（含 3.3.7.1–3.3.7.6）** | ★ 本版本部署产物整理完善（A SQL 重组 主体 + 规则/执行流程/摘要/失败处置/下游协作） | `release-3.md` |
| **3.3.7.7 / 3.3.7.8** | ★ B 部分 部署目录完善 + C 部分 跨版本工具目录整理 | `release-4.md` |
| **3.3.7.9** | ★ D 部分 双轨部署基线产出（约定 37 全量轨 + 增量轨校准 + 机器门；`--no-tag` 跳过，可 `--rebuild-baseline` 补跑） | `release-4.md` |
| **3.3.8** | ★ 生成版本测试报告（取最终验收 build，单文件 HTML） | `release-4.md` |
| **3.3.9** | ★ 整理 docs/references（对外需求归档 + 已满足标注） | `release-4.md` |
| **3.3.9.5** | ★ 收口**本版本**开发期变更台账（收口点 3；⛔ **必须先于 3.3.10**——台账内容此时尚未写回各族内容主文档，先合并主文档会让这批内容永久缺席）| `release-5.md` |
| **3.3.10** | ★ 版本规划文档整合（补充合并回主文档 + 清除废弃/延期需求） | `release-5.md` |
| **3.3.11** | ★ 全量详细设计生成（仅正式发布；**默认走变更范围增量**——只重算本次动过的专题、其余前滚，`--full-rebuild` 才全量重算） | `release-6.md` |
| **3.3.12bis** | ★ 零残留断言发布总闸（打 tag 前，⛔ 不接受任何 `skipped`；约定 33） | `release-6.md` |
| **3.3.13** | ★ 代码内版本标识对齐检查（打 tag 前最后一道；Important 级不硬阻断，无人值守 WARN + 自动登记欠账） | `release-6.md` |
| **3.4** | 打 Git 标签 + 创建版本分支并自动提交推送（3.4.1 提交 / 3.4.2 打 tag / 3.4.3 推送 / 3.4.4 失败处置） | `release-7.md` |
| **3.5 / 3.5bis / 3.6** | 更新项目记忆文件 / ★ baseline 历史版本归档（打完 tag 即搬，主文件留墓碑）/ 输出发布报告（含顶部欠账块） | `release-7b.md` |

> 收口：Step 3.6 完成 → 发布结束。**执行前务必已按 Step 进度 Read 对应 `release-N.md` 并逐项完成。**

---

## 情况 C：版本已发布

> ★ **与「版本落点决策门」的关系（交叉引用）**：re-release 是**版本已发布后又来新增量时的一条合法落点**——但**默认不该走它**。用户带新需求/bug 停在已发布版本时，入口 `/sprint-dev` Phase 0B.0 / `/sprint-bugfix` Phase 0C.0「版本落点决策门」会让用户三选一（落回 re-release / 新开 patch / 新开 minor），**re-release 仅在用户显式选择时才走本情况 C**。⚠️ **tag 移动风险**：本情况 C 会**强制移动已推送的 tag `v{x}` + 强制重建版本分支 + 强制推送**；**若该 tag 已被他人拉取 / 被 CI / 制品库消费，强制移动有实际风险**——正因如此它不能由执行体默认裁量、必须经用户在决策门显式选定（无人值守保守默认走"新开 patch、不动 tag"、绝不自动 re-release）。

**版本已处于「✅ 已发布」状态时再次执行 `/version {version}` = 重新发布（re-release）**（不是错误）：⛔ **入口即过改写授权门**（白名单第 4 处；与 Step 3.4.2.2 同一门，按最早触达点问一次，结果经 baseline `release_force_authorized` 传到 3.4.2）——**交互式**二选一（①授权重新发布 ②中止改用新补丁号）；**无人值守拒绝重新发布、直接退出**，不重写任何已发布文档。获授权后置 `REPUBLISH=1` 走版本发布流程（B-3）——自动关闭所有未关闭 Sprint（Step 3.1）、重跑发布产物、重打 tag + 重建版本分支指向本次新发布提交（Step 3.4.2 REPUBLISH 分支）+ 推送。除该门外全程不弹窗，仅终端 WARN：

```
♻️ 版本 {version} 已发布，本次为【重新发布】：将强制重打 tag v{x} + 重建版本分支 V{x} 指向本次新提交并强制推送。
```

> 只想补充设计/文档而非重新发布 → 另开补丁版本号 `/version V?.?.?`（里程碑名可省略由 Step 2.1.5 自动派生，或显式 `/version V?.?.? "M? hotfix"`）。

## 关键产物速查

| 产物 / 行为 | 权威 Step |
|------------|----------|
| 规划/发布模式自动判定 | [Step 1](#step-1判断执行模式) |
| 版本历史表（`memory/{version}/{user}/progress.md`，跨用户以最早规划者为权威） | [Step 2.5](../flows/version/planning-8.md) / [Step 3.3](../flows/version/release-2.md) |
| 代码内本应用版本号（`pom.xml` / `package.json` / `build.gradle` / `Cargo.toml` / `pyproject.toml` / `Dockerfile`）随版本号同步 | **规划期改齐** [Step 2.7.3](../flows/version/planning-8.md) → **发布期复核兜底** [Step 3.3.13](../flows/version/release-6.md)（同一实现 `{{AIDP_HOME}}/scripts/check_version_identifier.py`）|
| 未关闭 Sprint 自动 `/sprint-close` | [Step 3.1](../flows/version/release-1.md) |
| 版本更新日志.md（版本概览表 + 详情区块，倒叙置顶） | [Step 3.3.5](../flows/version/release-2.md) |
| 打 tag + 自动 commit/push | [Step 3.4](../flows/version/release-7.md) |
