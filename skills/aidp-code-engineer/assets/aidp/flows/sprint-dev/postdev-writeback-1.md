> **分片 1/3**：本片覆盖 Step X.0.0 上游级联检测。进入回写段须按序 Read 本片、`postdev-writeback-2.md`（X.0–X.7）和 `postdev-writeback-3.md`（X.8）；不得只读单片。

# sprint-dev · 开发完成后回写详情（Step X.0.0–X.8）
>
> ⚠️ **权威性**：进入回写段后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤（尤其 Step X.0.0 约定 22 四级级联触发、Step X.7 约定 25 配置项清单、Step X.8 约定 25 部署流程检测驱动）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；本回写段已二次切分为 `postdev-writeback-1/-2/-3.md` 三片，改动后同步各自 bundle 副本 `assets/aidp/flows/sprint-dev/`。理据/根因见同目录 `rationale.md`。

---

## ★ 开发完成后：自动回写需求 + 设计文档（含研发需求回写）

**触发条件**：开发过程中引入了以下任一变更，必须同步到上游文档：
- 新增接口 / 修改接口签名
- 新增数据库表 / 修改表结构 / 新增字段
- 新增公共组件 / 页面 / 业务模块
- 新增外部服务依赖
- ★ 调整 context-path / 端口 / proxy 路径 / API 前缀（这类**配置事实**变更必须回写到 `*事实清单.md` 的「⚠️ 本次变更」表 + 主表对应行；不回写 = 下次 /sprint-design 回检会把当前代码判为"凭印象推断"）
- ★ **开发期发现"需求漏项"**—— PRD/研发需求未提但本 Sprint 实际实现的功能点。分支 A 场景常见（已规划 Sprint 开发到一半发现遗漏）；分支 B 场景已由 Phase 0B.1.1 提前处理，本 Step X.0 不再重复

### 回写步骤

#### Step X.0.0：★ 上游文档级联同步检测

**目的**：开发完成后自动分析本 Sprint 是否影响 4 份核心上游文档（**研发需求 / 详细设计 / 研发执行计划 / 研发自测用例**），按级联规则触发对应 SKILL / 命令补充模式，避免"代码已改、文档未跟"。

**与 Phase 0B.1.1 的关系**：分支 A（已规划）以 X.0.0 为开发后补文档主路径；分支 B（口述累进）以 0B.1.1 为开发前主路径，X.0.0 只补后续新漂移。两者共用级联触发链，但 X.0.0 用 `--ledger-cascade` 就地改各族主文档，不重复 0B.1.1 的 `NN_<业务主题>.md`。权威定义见 Phase 0B.1.1，根因见 `rationale.md`。

**执行（命令端自动）**：

1. **生成变更影响清单**（命令端用 Bash 扫描，输出表）：

   ```bash
   # vcs_mode=git：信号源 = 本 Sprint 起始 commit ↔ HEAD
   git diff {sprint-start-sha}..HEAD --stat
   git log --oneline {sprint-start-sha}..HEAD
   # vcs_mode=none：禁用以上 Git 命令，改取下面的逐文件 sha256 前后态（含新增/删除）
   # 接口信号
   grep -rE "@(Get|Post|Put|Delete|Patch)Mapping|@RestController" code/backend/ | grep -v test
   # DDL 信号
   grep -rE "CREATE TABLE|ALTER TABLE|ADD COLUMN|DROP COLUMN" docs/deployment/{version}/sql/增量/
   # 页面/组件信号
   ls code/frontend/{子项目}/src/views/ ; ls code/frontend/{子项目}/src/components/
   # 业务规则/状态机信号（grep 关键注释关键词）
   grep -rE "// 状态机|// 业务规则|@Enum|TODO\[GAP\]|❓ 待澄清" code/
   ```

   `vcs_mode=none` 时先执行以下本地对账（`SNAP`/`CHANGES` 均按真实版本、身份、Sprint 编号展开；缺快照直接非零，不可空结果放行）：

   ```bash
SNAP="memory/{version}/{user}/sprints/sprint-{NNN}-local-before.json"
CHANGES="memory/{version}/{user}/sprints/sprint-{NNN}-local-changes.json"
SNAP="$SNAP" CHANGES="$CHANGES" VERSION="{version}" python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
snap, output = Path(os.environ["SNAP"]), Path(os.environ["CHANGES"])
if not snap.is_file():
    raise SystemExit("evidence-missing: Sprint 开发前文件快照缺失")
before = json.loads(snap.read_text(encoding="utf-8"))
roots = [Path("code"), Path("env"), Path("docs/deployment") / os.environ["VERSION"]]
after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
         for root in roots if root.exists() for p in root.rglob("*") if p.is_file()}
changed = [{"path": p, "before_sha256": before.get(p), "after_sha256": after.get(p),
            "kind": "added" if p not in before else "deleted" if p not in after else "modified"}
           for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
output.write_text(json.dumps(changed, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"本地文件变更：{len(changed)}；证据：{output}")
PY
   ```

   输出 `memory/{version}/{user}/sprints/sprint-{NNN}-upstream-impact-{YYYYMMDD-HHMM}.md`：

   | # | 检测维度 | 变更内容 | 涉及代码位置 | 受影响上游文档 | 建议补充级别 |
   |---|---------|---------|------------|--------------|------------|
   | 1 | 新增接口 | POST /api/order/export | OrderController.export | 详细设计.md / 接口设计.md | L2+L3+L4 |
   | 2 | 新增表 | t_order_export_log | {NN}_订单导出日志表DDL.sql | 数据库设计.md | L2+L4 |
   | 3 | 新增业务规则 | 导出 >10000 行需异步 | OrderExportService.exportAsync | 详细设计.md | L2+L4 |
   | 4 | 需求漏项 | 导出格式选项 CSV/XLSX/JSON | UI 多选 + 后端分支 | **01_研发需求.md** | L1+L2+L3+L4 |
   | 5 | 计划偏差 | Sprint-{NNN} 实际工时 8d vs 计划 5d | 工时记录 | 01_研发执行计划.md | L3+L4 |
   | 6 | ★ 第三方 Mock→真实对接 | 第三方交付后切真实（删 Mock 桩/拦截、`VITE_USE_MOCK` 或 `@Profile("mock")` 关、`.env.*` baseURL 切真实端点）| xxxClient / .env.* / mock 开关 | **01_详细设计.md / 03_接口设计.md**（契约变了 +**01_研发需求.md**）| L2+L3+L4（契约变 +L1）|

   > **`vcs_mode=none` 确定性本地证据**：在任何 Phase 0A.5 删除或 Phase 1 代码改写之前，`sprint-dev.md` 已将 `code/`、`env/`、本版 `docs/deployment/` 文件内容哈希存至 `memory/{version}/{user}/sprints/sprint-{NNN}-local-before.json`。本步按同样三棵目录再算 sha256，路径并集逐项比较前后值（含新增/删除），形成带 `path / before_sha256 / after_sha256 / kind` 的变更清单；再从**这些实际变化的文件**提取接口、DDL、页面、业务规则与配置事实的具体内容，写入上述影响表。空 Git diff / 单纯扫描当前代码结构均不足以判「零漂移」；前态快照缺失或文件无法读取时记 `evidence-missing` 并审计本 Sprint 涉及的全部业务文件与上游文档，不得跳过 X.0/X.2/X.3。`DEV_FILES` 与 X.7 都消费**这一份相对路径清单**，不得各用一套判据。
   > 本步骤在 `vcs_mode=git` 的 git diff + 代码结构对比 + 维度判定即「变更检测」的权威实现；`postdev-writeback-2.md` 的 Step X.2~X.3 仅在用户绕过 X.0.0 直接走兜底人工模式时单独触发。
   >
   > ★ **检测项 6「Mock→真实对接」要点**（约定 22 + 约定 26 阶段②/④）：切真实常**不表现为新增接口**（接口名没变、只是实现换成真实 client + baseURL），故易漏判。（余下理据见同目录 `rationale.md`）

   **跳过条件**：若清单为空（本 Sprint 完全按既存文档实现，零漂移）→ 终端打印「✅ 无上游文档变更，跳过 X.0/X.2/X.3」，直接进入 X.4。

2. **落盘形态锚定**：本段四级一律走 `--ledger-cascade` **直接改各族内容主文档正文** + 刷该目录 `00_索引.md` 生成时间；⛔ 不新建分册、⛔ 不占 `NN_` 序号（那是产品侧/口述累进的命名空间）。**无需锚定 NN**。落盘规则详见 `{{AIDP_HOME}}/reference/开发期族增量.md`「收口执行要点」第 3 条。

3. **★ 用户决策门**（两种模式）：
   - **★ `--unattended`（autopilot `/loop` 无人值守）**：**绝不弹窗**——默认走下方选项 **(1) 自动级联补充**（4 文档级联同步是既定动作、非需人拍板的选择）；影响清单 `sprint-{NNN}-upstream-impact-*.md` 照常留档以便复盘。仅当 PRD `autopilot_decisions.on_decision_conflict` 声明 `pause`/`pause-notify` （后者额外发里程碑通知）且本轮命中「决策冲突」才转失败处置交人工。
   - **交互式（默认，用户在场）——★ 默认自动级联、不阻塞、无"跳过"口子（与 `--unattended` 一致）**：检测到上游文档变更后**默认直接走下方选项 (1) 自动级联补充**，无需征询用户即串行触发 L1→L4 补充；影响清单照常留档；**不弹 `AskUserQuestion`、无"(3) 跳过此次"选项**。
     - **唯一确认例外（破坏性变更门）**：仅当检测到**跨主文档破坏性变更**——主文档正文语义被推翻/删除而非纯增量（删既有接口/表/字段、既有业务规则被反转、既有 Sprint 拆分被推翻重排）——才用 `AskUserQuestion` 让用户确认（选项：① 按破坏性变更级联并在增量文档标注"结论取代"/ ② 保留旧结论仅追加新增量）。**普通增量（新增接口/表/字段/规则/用例）一律自动级联、不弹窗。**
     - **禁止降级为自由反问**：无论交互式还是无人值守，**都不得**以"变更较多/稳妥起见/要不要先这样"为由把本门降级为自发的范围/进度确认（见文首硬约束「统一决策纪律」）；所有决策只能走本步的结构化选项。

3.5. **★ 改动量档位判定门（`dev_scale`）——级联的【承载形态】按改动量伸缩，触发级别与硬门一律不变**

   > ⛔ 档位仅伸缩承载形态，绝不裁剪级联：L1 需求留痕、L4 自测用例、约定 22 检测项与触发级别任何档位都必须执行。动机见 `rationale.md`。

   **判据（命令端确定性计算，与 Step 2.4.1.5 同精神）**：

   ```bash
   # 本 Sprint 实际改动的【业务代码】文件数（排除文档/配置产物，只数 code/ 下真实代码）
   # 四个来源取并集：未暂存、已暂存、未跟踪、已提交未推送；漏未跟踪文件会误判改动量为零。
   DEV_FILES=$( { git diff --name-only -- code/
                  git diff --cached --name-only -- code/
                  git ls-files --others --exclude-standard -- code/
                  git log --name-only --pretty=format: @{u}..HEAD -- code/ 2>/dev/null
                } | sort -u | grep -vE '^$|\.(md|json|ya?ml)$' | wc -l | tr -d ' ')
   ```

   **`vcs_mode=none` 用本地证据替换上面整段 Git 计数**（不可在 Git 命令得到 0 后回退 S 档）：`DEV_FILES=$(CHANGES="memory/{version}/{user}/sprints/sprint-{NNN}-local-changes.json" python3 -c 'import json,os; from pathlib import Path; p=Path(os.environ["CHANGES"]); assert p.is_file(), "evidence-missing"; print(sum(x["path"].startswith("code/") and not x["path"].endswith((".md",".json",".yaml",".yml")) for x in json.loads(p.read_text(encoding="utf-8"))))')`。删除文件也计入改动，快照/清单缺失则停止档位自动判定并补证据或按 L 档审计，不得判 S。

   `HAS_API` / `HAS_DDL` / `HAS_SEMANTIC` / `HAS_CONFIG` 取自**上一步已产出的检测项表**（1 新增接口 /
   2 新增表 / 3 新增业务规则 · 6 Mock→真实 · 语义口径变更 · 新增配置项），不另行判定、不与其冲突。

   | 档位 | 判据 | 级联**承载形态** |
   |------|------|-----------------|
   | **S** | `DEV_FILES≤2` 且 `!HAS_API` 且 `!HAS_DDL` 且 `!HAS_SEMANTIC` | 四级都追加进各族增量文件，档位只决定**写多少**：**L1** 需求留痕不可省（只写本次涉及的功能点）；**L2** 只写受影响小节，接口/数据库无变更即不写；**L3** 只更新受影响 Task 条目；**L4** **照常产增量用例**（硬门，见上）|
   | **S（语义子档）** | `HAS_SEMANTIC` 但 `DEV_FILES≤6` 且 `!HAS_API` 且 `!HAS_DDL` 且 `!HAS_CONFIG` | 同 S **+ 强制「受影响结论清单」** |
   | **M** | `3≤DEV_FILES≤10` 或 `HAS_API`（未命中 S） | 四级全量追加（各族增量文件写全）|
   | **L** | `DEV_FILES>10` 或 `HAS_DDL` 或契约变更 | 同 M **+ 部署基线联动**（约定 37 增量轨 / 约定 25 配置项清单）|

   **判定顺序**：先判是否命中 S（四条全满足）→ 再判是否命中 **S 语义子档** → 否则 M → 否则 L。**含建表 / 契约变更一律 ≥ L**（安全兜底，同 Step 2.4.1.5）。

   **★ S（语义子档）的强制伴生项 =「受影响结论清单」**（动机 + 下游实测数据见同目录 `rationale.md`）：
   在 L1 需求留痕里产一张**逐条打勾**的表——列 = `# / 受影响落点（需求条目·ADR·用例断言·反向断言·
   铁律注释·REQ-XXX 代码注释）/ 位置 file:line / 旧结论 / 新结论 / 处置`；**空表或只写整体描述 = 未产出**。
   ⛔ 清单属**级联保证**、不属**档位承载**：任何档位都不省，S 语义子档只是**强制显式化**。

   - **落盘留痕**：写 baseline `versions.{V}.sprints.{NNN}.dev_scale`（`{tier, dev_files, has_api, has_ddl, has_semantic, has_config, at}`），供复核"这轮为什么只产一份增量"。
   - **打印**：`📐 改动量档位：S（2 文件 / 接口=否 表=否 语义=否）→ L2 就地追加小节、L1+L4 照常产增量`。
   - **用户覆盖**：`/sprint-dev … --dev-scale=S|M|L` 显式覆盖自动判定（留痕 `source:"user"`）。
   - **档位必须传给下一步四级级联**（`--scale={dev_scale}`），不得只写 baseline；缺省会回退 L 档。
   - **档位不影响的东西**：约定 22 检测/触发、L1 留痕、L4 用例、S 语义子档「受影响结论清单」、影响清单、破坏性确认、Sprint 归档和 memory 状态同步，任何档位均保留。

3.8. **★ 攒批而非即时级联（默认行为）——写台账，不当场跑四级**

   > ⛔ **本步若由子 Agent 执行**：派单简报必须带 `cascade_mode` + `dev_scale`，且 `ledger` 时
   > **不得罗列待改文档清单**（罗列 = 强制 `--cascade-now`，机制当场失效）。契约见「子 Agent 执行时的派单契约」。

   > **单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`**（台账路径/格式/条目编号/收口点清单/清理规则/
   > 跨版本落点全在那份，本处**不复述**，只说明本步该做什么）。**进入本步第一动作 = Read 该文件。**

   把上一步影响清单的每一行**按受影响的族追加为增量册条目**（四族落点见
   `{{AIDP_HOME}}/reference/开发期族增量.md`；跨族**共用同一 `C-NNN`**、各记各的那一面，⛔ 不复述别族）
   （**不存在则从 `{{AIDP_HOME}}/templates/_开发期族增量.md` 拷贝骨架，⛔ 别自拟格式**——
   条目形态是 `pending_cascade()` 的机器判据，改写法它就一条都认不出、收口点永不触发），**然后直接跳到 Step X.4，本轮不跑四级级联**（X.0/X.2/X.3 就是四级级联本身，须整段跳过）。

   - **台账条目只记一行**：`- C-{NNN} · MM-DD HH:MM · 一句话 · sprint-{NNN}`，附必要的 🔴破坏性标记；不重复记录代码落点、L1~L4 级别、变更类型或档位。详述放影响清单，一句话无法概括时用 `--cascade-now`。
   - **攒批期间 append-only**：只追加、绝不改删已有条目。
   - 🔴 **破坏性变更同样进台账**（项目方知情选择：一律攒、不设例外），但**必须**① 条目标 `🔴 破坏性`
     ② 在台账「⚠️ 已知失准点」段登记**具体失准位置**（哪份文档哪一节现在是错的）。
     ⚠️ 这是本机制**唯一的已知风险敞口**：增量攒着只是"文档暂时不全"，破坏性攒着是"文档明确是错的"。
   - **原影响清单 `sprint-{NNN}-upstream-impact-*.md` 照常产出**（单次复盘用），两者不互相取代。
   - **★ 例外：`--cascade-now` 立即级联**。带该 flag 时**跳过攒批、当场跑完四级级联**（用于当轮就要拿到
     自测用例的场景——收口点不含 `/sprint-close`，当天开发当天关闭的 Sprint 需要它兜底）。
   - **打印**：`📥 已记入开发期变更台账 C-0NN（共 N 条待级联）；将于下次收口点批量级联`。
   - **同时在原影响清单末尾追加** `📥 已入台账 C-0NN..C-0MM（攒批，待收口点级联）`，作为合法终态标记；否则下轮会重复级联。

4. **级联触发规则**（★ **仅在收口点或 `--cascade-now` 时执行本步**；默认走上一步 3.8 攒批。
   收口时按台账**合并后**的总改动量重判档位，再按下表调用）：

   触发条件 → 触发哪一级的判定**按 CLAUDE.md 约定 22「4 级触发表」**（★ **逐条目独立判定、不按整轮取最大值**）。本步骤仅给出每一级对应的命令/SKILL 调用映射：

   > ⛔ 各级调用必须传递本次改动量 `--scale={dev_scale}`，由命令继续透传给 SKILL；不得误传整版 `req_scale`。漏传会回退 L 档。用例数与分册口径见各 SKILL，根因见 `rationale.md`。

   | 级 | 触发时调用（★ 均带 `--scale={dev_scale}`）|
   |----|-----------|
   | L1 研发需求 | 经 `/sprint-requirements --ledger-cascade [--unattended]` 编排（内部 `ux-logic-extractor` 增量 prompt 驱动）→ **就地改** `01_研发需求.md`。该命令无 `--scale` 入参 → **在调用 prompt 里以自然语言传达档位与目标篇幅**（S 档：只写本次改动涉及的功能点增量，不重述既有需求）|
   | L2 详细设计 | `dev-logic-architect`（增量 prompt 驱动）→ **就地改** `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围；通过 `/sprint-design --ledger-cascade --scale={dev_scale} [--unattended]` 编排）|
   | L3 研发执行计划 | `dev-execution-planner`（增量 prompt 驱动；通过 `/sprint-plan --ledger-cascade --scale={dev_scale} [--unattended]` 编排）→ **就地改** `01_研发执行计划.md` |
   | L4 自测用例 | 经 `/sprint-selftest --ledger-cascade --scale={dev_scale} [--unattended]` 编排（内部 `dev-manual-testcase` 增量 prompt 驱动）→ **就地改**既有用例册。★ **用例数基线机检须同样显式传档**：`check_case_stats.py <路径> --scale {dev_scale}`（不传按 L 档只判 20 条硬下限）|

   级联铁律见约定 22；触发条件矩阵（"仅设计层变更"何时触发何级等）以约定 22 表为权威，本步骤不复述。

5. **执行 + 留档**：
   - 链路按上表逐级执行；每级 SKILL 输入显式包含上一级补充文档 + 既存基线 + 本 Sprint 代码现状
   - 任一级 SKILL 失败 → 暂停链路，保留已生成的下游 stub，提示用户人工接管（不静默继续）
   - 成功完成后在影响清单文件末尾追加：`✅ 级联执行结果：L1-OK / L2-OK / L3-OK / L4-OK`（缺级标 `-`）
   - 各目录 `00_索引.md` 追加本轮增量行（类型=补充 + 生成时间）

6. **级联未完成的留档兜底**（本兜底只针对**级联链中途 SKILL 失败暂停**、`skip-doc-sync` 显式跳过、或破坏性变更门未及处理等"未消化"残留）：
   - 影响清单文件保留在 `memory/{version}/{user}/sprints/` 目录
   - 下一次 `/sprint-dev` 启动时（无论分支 A/B），命令端在**分支 A/B 共用入口**（分支 B 无 Phase 0A，不能只挂 0A 末尾）扫该目录，若发现"未消化"的影响清单（**既无 `✅ 级联执行结果` 行、也无 `📥 已入台账` 行**——两者都是合法终态：前者=已级联，后者=已攒批待收口）→ **默认自动补跑级联**（走本步选项 (1) 口径）补齐上轮残留 + 终端 WARN"已自动补齐上轮未消化的上游变更"；仅命中"破坏性变更门"才弹确认，**不再以普通增量为由反问用户**

