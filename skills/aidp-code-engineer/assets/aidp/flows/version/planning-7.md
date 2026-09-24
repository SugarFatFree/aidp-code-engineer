# /version · 版本规划流程详情 — 分片 7/8

> 本片覆盖：**Step 2.4.7 版本规划产物全量审计（独立子 Agent；强制铁律）**。
> 完整分片清单见 `{{AIDP_HOME}}/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
#### Step 2.4.6.5：★ 调用前机械预检（先把确定性检查器跑齐，再谈独立审计）

四族产物落齐后，**先运行各阶段既有确定性检查器**，把每个检查器的
`source / executed / exit_code / output_present / findings[]` **真实结果**汇总成一份 JSON，
再用聚合器一次列出全部问题：

```bash
python3 {{AIDP_HOME}}/scripts/version_preflight.py --input <检查结果清单.json> --json
```

- ⛔ **不可用、未执行、空扫描或空输出一律不算通过**：`executed=false` / `output_present=false` /
  `scanned_files=0` / `skipped=true` / 异常退出码 → `status=unavailable|block`，
  必须先定位原检查器并修复或补跑，再复查预检。
- ⛔ **不适用的检查器要写明依据后移出本轮预期集合**，⛔ **不得把应跑项移出集合来掩盖失败** ——
  两者在输出上长得一样，区别只在有没有写依据。
- 检查器产出 JSON 时**按其真实字段映射**，⛔ 不猜字段、⛔ 无结果不造空 `findings`
  （造一个空数组等于把"没跑"伪装成"跑了且干净"）。
- 相同缺口按 `check_id + file + anchor` 合并展示，保留原始来源与**最高**严重度。
- ★ **本聚合器不替代任一检查器，也不替代 Step 2.4.7 的八项独立审计** ——
  它只回答「该跑的都跑了吗、结果长什么样」，不回答「产物对不对」。
- 发现一处旧术语 / 旧口径时，**先在本轮受影响文档与代码注释里穷举同义残留**再按原入口修，
  ⛔ 避免每轮只修一处、同一问题跨版本复发。

#### Step 2.4.7：★ 版本规划产物全量审计（独立子 Agent；强制执行铁律）

> **定位**：4 子文档生成 + Step 2.4.5/2.4.6 命令端校验之后、Step 2.5+ 落盘 `memory/` + `CLAUDE.md` 之前的最后一道**独立审计关**。由独立子 Agent 执行，与 4 个 SKILL 完全解耦，按约定 21 不复述 SKILL 维度，只做"产物外部审计"。

> ⛔ **强制执行铁律**：本 Step **必须执行**；唯一允许跳过的条件见下方「唯一允许跳过的条件」段（权威声明）。Agent **不允许**以"节省上下文 / 节省 token / 本次任务简单 / 跑得太久了 / 上下文已经很长 / 用户应该可以接受跳过"等任何借口自行决定跳过本 Step；任何输出"本次为节省上下文未跑独立审计 agent"的话术都视为**违反铁律**。

> 📌 **独立子 Agent 上下文隔离机制**（必读）：
> - `Agent` 工具调用的独立子 Agent 跑在**隔离的对话上下文**里，与主对话完全不共享上下文窗口；主对话只接收子 Agent 返回的**最终结果**（JSON 摘要 + 报告路径），通常 ≤ 几百行 token
> - 子 Agent 内部读取 4 类产物 / 跑 grep / 写审计报告等过程产生的所有中间 token **不计入主对话上下文**
> - 主对话因 Step 2.4.7 增加的 token 仅为：① 调用 Agent 工具的语句本身（≤ 30 行）② Agent 返回的最终摘要（≤ 200 行）→ **不会爆主上下文窗口**
> - 反过来理解：Agent 跑得"上下文很长"的恐惧针对的是**主对话累积上下文**；本 Step 用独立子 Agent 正是为了**绕开主上下文限制**做横向审计 — 跳过它 = 反向破坏设计目的
> - 子 Agent 按 token 计费（与主对话一致），但**不影响主对话的剩余上下文配额**

**为什么需要这一步**：
- SKILL 内部 QR 主要管"自身维度"，对**跨产物的一致性**（如自测用例是否覆盖了研发需求所有 REQ、研发执行计划是否引用了详细设计的所有锚点）缺乏端到端视角
- 命令端 Step 2.4.5/2.4.6 已校验"关联文档表头/路径有效性"，但**不审计**"产物覆盖 PRD 的完整性"+"产物未越界"+"引用密度逐段达标"
- 增量版本场景下，需要对比 `prev_version` 的产物 + `code/` 已落地事实，判断本版本产物是否只覆盖新增/变更需求 → 这是 SKILL 单文档生成时拿不到的横向比较
- **本 Step 由独立子 Agent 执行的意义就是"让审计跑在隔离上下文"** — 主对话即使已经很长也不影响审计 Agent 工作，跳过它 = 反向破坏设计目的

**★ prev_version 取值口径（规划期 = 上一【迭代】版本，含未发布的中间过渡版本）**：

规划期的"上一版本"**不是** `release-1.md`「tag 风格识别约定」定义的「上一已发布版本」——当前版本未发布时用户直接开下一版规划是**合法操作**（该版即中间过渡版本，见约定 2 细则「中间过渡版本」），若按 tag 取值就会**跳过过渡版本**，令 D 增量一致性审计把过渡版本已交付的内容重判为"新增"、H 跨版本作废清算（约定 34）读不到过渡版本的历史需求而漏检结论反转。故本 Step 按**产物目录 SemVer 扫描**取值（与 `/sprint-selftest` Step 1 的「前置：定位上一版本继承基线」同一范式，见 `{{AIDP_HOME}}/flows/sprint-selftest/step-1-1.md`；⛔ 该命令无 `Step 1.1`，那是分片文件名）：

```bash
CUR_V="{version}"
PREV_VERSION=""
for d in $(ls -d docs/requirements/V*/ 2>/dev/null | sed -E 's#.*/(V[^/]+)/#\1#' \
           | grep -E '^V[0-9]+\.[0-9]+\.[0-9]+$' | sort -V); do
  [ "$d" = "$CUR_V" ] && continue
  [ "$(printf '%s\n%s\n' "$d" "$CUR_V" | sort -V | head -1)" = "$d" ] || continue  # 只留 < 当前版本
  [ -d "docs/requirements/$d/研发需求" ] && PREV_VERSION="$d"   # 取最近一个有研发需求产物的旧版本
done
echo "prev_version=${PREV_VERSION:-null}"   # 空 = 本版为首版（无可比基线）
```

> 发布期口径不受本节影响：`版本更新日志.md` 的对比区间与 tag/版本分支识别**仍取「上一已发布版本」**（`release-1.md`）——过渡版本从未对外发布，其变更应并入本次发布条目，两处口径刻意不同。

**★ Δ 范围裁剪（补充模式 B-2 适用；fresh 模式不裁剪）**：审计 C-4 / C-5 / F 是**逐条反向覆盖核对**，成本随本版产物体量线性涨。补充模式下本版只动了部分专题，无须对全部主文档重做逐条核对——按 `release-6.md`「变更专题重算 + 其余前滚」同一范式先算出 Δ，再把 Δ 连同**保守扩散规则**一并传给审计 Agent：

```bash
# ⛔ `PREV_VERSION` 赋在上一围栏（另一次 Bash 调用）→ 本围栏取空 ⇒ `--since` 缺实参，
#    补充模式 B-2 的审计 Δ 范围裁剪拿不到基线。故就地重算一次（口径同上一围栏）。
PREV_VERSION=""
for d in $(ls -1 docs/requirements/ 2>/dev/null | grep -E '^V[0-9]+\.[0-9]+\.[0-9]+$' | sort -V); do
  [ "$d" = "{version}" ] && break
  [ -d "docs/requirements/$d/研发需求" ] && PREV_VERSION="$d"
done
python3 {{AIDP_HOME}}/scripts/code_inventory.py delta --since "${PREV_VERSION}" --json   # 本版代码事实 Δ
# 文档侧 Δ = 本轮新产出的 NN_ 增量文档 + 其覆盖的专题
```

- **保守扩散（照抄 release-6 的安全网，别自创）**：命中约定 22 第三类语义变更、或表 F 判「作废/修订」的项 → 其受影响专题**强制并入 Δ**（即便无文件命中）；变更落在**跨专题共享单元**（公共基础设施 / 基类实体 / 共享 DTO / 全局配置）→ 把所有引用该单元的专题并入 Δ。**宁可多算一个专题，绝不漏传播一处语义。**
- **⛔ 裁剪只作用于 C-4/C-5/F 三项的核对范围**，不裁剪审计项本身：A/B/D/E/G/H 一项不减，且 **Δ 内的核对仍是逐条、不降标准**。
- **fresh 模式（首次为本版生成全部主文档）不裁剪** —— 那时"全部产物"本来就等于 Δ。
- 无法可靠算出 Δ（`delta` 报无快照 / 台账缺该版）→ **退回全量核对并在报告注明**，不得因算不出 Δ 就跳过核对。

**调用方式**：

使用 `Agent` 工具（subagent_type 留空走 general-purpose 默认；或显式配 `claude` 通用 agent）直接调用 `{{AIDP_HOME}}/agents/version-auditor.md` 定义的独立子 Agent：

```
Agent(
  description: "版本规划产物全量审计",
  prompt: <<PROMPT
读取并严格按照 {{AIDP_HOME}}/agents/version-auditor.md 的「三、审计八项」+「四、审计报告输出」工作流执行，
对版本 {version} 的 6 类规划产物（研发需求 / 详细设计 / 研发执行计划 / 研发自测用例 / 研发自测方案 /
测试环境与账号；与 `planning-5.md` 三步落盘自检同口径，version-auditor 按「需求 / 设计 / 计划 / 自测」
4 组归类，自测组含后 3 类）+ 原型内容基线做全量审计。

调用上下文：
- {version} = {当前版本号}
- mode = {fresh / supplement-NN}  （从 memory/{version}/.aidp-inputs-snapshot.json 的 snapshot_run 字段读取）
- prev_version = {上一迭代版本号；无则填 null}  （按上方「prev_version 取值口径」的产物目录 SemVer 扫描取值，**含未发布的中间过渡版本**；不取 tag）
- scale = {S / M / L}  （★ 必传：读 baseline `versions.{version}.req_scale.tier`，Step 2.4.1.5 判档时已留痕；
  读不到填 L。**漏传会让 S 档必然误判阻塞**——S 档按 SKILL 约定只产 1 册合并详设、Step 2.4.4 还会
  主动把多册合并回 `01_详细设计.md`，而审计的 A-03/A-04 若不知档位就会报"接口/数据库设计分册缺失"两个 Critical，
  `--unattended` 下 3 轮自动修复也修不好（修法与档位互斥），最终返回 audit-block 让 autopilot 熔断冻结。）
- 产品 PRD 路径 = docs/requirements/{version}/产品提供/
- 原型路径 = docs/prototype/{version}/code/ + docs/prototype/{version}/mockup/
- 6 类规划产物路径 = 按 version-auditor.md 二·必读清单第 4~9 项（第 9 项含研发自测方案 + 用例 + 测试环境与账号）

输出要求：
1. 写盘审计报告到 docs/audit/{version}/version-output-audit-YYYY-MM-DD.md（补充模式用 -补丁-NN.md）
2. 返回结构化 JSON 摘要（按 version-auditor.md 五·与命令端的交互协议 输出格式），包含 overall、items、fix_actions
3. 报告必须含 A/B/C/D/E/F/G/H 八项逐项详情 + 修复建议 + 命令端下一步建议

铁律：
- 不修改 4 类产物本体
- 不复述 SKILL 内维度（按约定 21）
- 增量版本必须对比 prev_version + memory/databaseBaseline.md + code/ 已有事实
PROMPT
)
```

**审计八项**（Agent 内部执行，命令端只看摘要）：

| 项 | 名称 | 关注点 |
|----|------|--------|
| A | 存在性 | 6 类规划产物文件齐全（必备 + 拆分形式兼容；含研发自测方案 + 测试环境与账号） |
| B | 边界 | 4 类产物互不越界（需求里无 SQL/Java 类、详设里无 Sprint 排期等） |
| C | 覆盖完整性 | PRD 功规点 100% 映射到 4 类产物；**并下探反向覆盖**（C-4 PRD 表行级原子条目→研发需求、C-5 研发需求字段→详细设计，漏项/漏列/未确认增列 Critical） |
| D | 增量一致性 | 仅增量版本：4 类产物只覆盖增量需求，未与上版本 + code/ 已有事实冲突 |
| E | 引用链 | 100% 引用密度铁律（研发需求→原型，详设→需求+原型，研发执行计划任务表列结构按 SKILL 定义，用例→需求+原型） |
| F | 原型覆盖度 | **Critical 硬门**：以「原型内容基线」为准，原型 `code/` 每个未标裁剪/延期/改逻辑的元素、交互态、操作逻辑是否被研发需求 + 详细设计覆盖（无原型 = N/A） |
| G | 语义变更派生完整性 | **Critical 硬门**（约定 22 第三类）：语义/口径/范围变更（无新增实体）类需求的派生展示物清单（表 E）是否三层贯通（研发需求→详细设计文案落点→用例反向断言）；无语义变更 = N/A |
| H | 跨版本需求作废完整性 | 约定 34：本版推翻历史需求时是否登记作废清单（表 F）+ 作废项代码残留是否已标注；无语义反转 = N/A |

详细审计项 + 评级阈值 + 结构化输出格式见 `{{AIDP_HOME}}/agents/version-auditor.md`，命令端不复述。

**命令端处置（基于 Agent 返回的 JSON 摘要 `overall` 字段）**：

> ⛔ **第四条分支不可省 —— Agent 调用本身失败 / 超时 / 返回非法 JSON**（拿不到 `overall`）：
> **重试 1 次**；仍失败 → **交互式**二选一（重跑 / 中止——确需跳过须用户以 `--skip-audit` 重新调用）；**无人值守**返回失败信号
> `audit-block`（`reason=auditor-unavailable`）交 autopilot 熔断。
> ⛔ **绝不因 Agent 不可用而视同 pass**：那样 `docs/audit/{version}/` 为空且无任何 flag，
> 与「跑了且通过」在终端上看不出区别——审计被静默跳过，规划产物就等于未经审计。
> （同流程 `planning-6.md` 的子 Agent 已有同款兜底，本步照其形态补齐。）

```
IF overall == "pass":
    输出 "✅ 版本规划产物审计通过（报告：<report_path>）"
    继续 Step 2.5

ELIF overall == "warn":
    输出 "⚠️ 版本规划产物审计通过但有警告（报告：<report_path>）"
    把警告摘要记入 Step 2.8 输出报告的「⚠️ 审计警告」区块
    继续 Step 2.5

ELIF overall == "block":
    输出 "❌ 版本规划产物审计未通过（报告：<report_path>）"
    ├─ **交互式**（未带 `--unattended`）→ 用 AskUserQuestion 让用户二选一：
    │     ① 自动按建议回调对应 SKILL 修复（推荐）—— 按 fix_actions[] 依次跑 `/sprint-requirements [--unattended]` / `/sprint-design [--unattended]` / `/sprint-plan [--unattended]` / `/sprint-selftest [--unattended]`（研发自测类修复走 `/sprint-selftest`），每个调用必须传 Agent 的 prompt_addon 增强 prompt；跑完后**重新触发 Step 2.4.7 Agent**
    │     ② 我手工修复 —— 暂停命令，用户修完输入 "继续" 后**重新触发 Step 2.4.7 Agent**（⛔ 不存在「忽略 block 继续」的选项；确需跳过只能以 `--skip-audit` 重新调用）
    └─ **无人值守**（`--unattended`，`/sprint-autopilot` `/loop` 透传）→ **绝不弹 AskUserQuestion 挂死**：自动按 fix_actions[] 回调 SKILL 修复 → 重审，最多 3 轮。⛔ **回调的每个 `/sprint-*` 都必须逐个透传 `--unattended`**——`/sprint-design` 的 0.5.5 确认门是 greenfield 首版必过的门，不透传即在这 3 轮自动修复里挂死，且比在主链上挂更隐蔽；**3 轮仍 block** → 不再询问，向调用方**返回失败信号 `audit-block`**（连同 report_path），交 autopilot「失败处置」熔断（#4 卡 + `dev_fail_streak`/`needs_human` 冻结，见 `sprint-autopilot.md` Phase 3 失败处置），绝不静默忽略继续、也绝不挂起等待。
```

**循环上限**：自动修复 → 重审 最多 3 轮；3 轮仍 block —— 交互式强制走 ② 让用户接管；`--unattended` 返回 `audit-block` 失败信号交 autopilot 熔断（见上分支，绝不弹窗）。

**唯一允许跳过的条件**：用户在 `/version` 调用时**显式传** `--skip-audit` 旗标 → 跳过 Step 2.4.7，但在 Step 2.8 输出报告里强制标"⚠️ 已跳过审计（用户显式 --skip-audit）"。**除此之外没有其他跳过路径**——任何 Agent 自行判断的"跳过"都是 BUG。

##### ⛔ Step 2.4.7 RED FLAG 反模式（见到这些念头立即停止跳过）

Agent 在执行 Step 2.4.7 前可能产生以下"跳过"念头，**全部都是误解 / 违反铁律**，必须忽略并强制执行审计：

| 错误念头 | 真相 |
|---------|------|
| "本次为节省上下文未跑独立审计 agent，让用户后续单独触发" | ❌ 独立子 Agent 跑在隔离上下文，**不占主对话窗口**；这种"为用户节省"是**误解机制**。Agent 必须直接执行 |
| "上下文已经很长了，再跑 Agent 会爆" | ❌ Agent 调用本身只增加 ≤ 30 行；子 Agent 内部读文件 / grep / 写报告全部在隔离上下文，主对话只接收最终 JSON 摘要 |
| "本次 PRD 简单 / Sprint 数少，应该不会有问题，跳过省事" | ❌ 是否需要审计 ≠ 是否容易出问题；审计就是为了发现 Agent 主观以为"没问题"的盲区 |
| "用户应该可以接受跳过 / 用户没要求一定要跑" | ❌ 设计语义就是默认必须跑；用户没传 `--skip-audit` = **明确要求跑** |
| "Step 2.4.6 已经校验得很全了，不需要再 audit" | ❌ Step 2.4.6 只看路径有效性，不看 PRD 覆盖完整性 + 引用密度逐段达标 + 增量一致性 |
| "Step 2.4.6 显示一切正常，audit 应该也是 pass，跳过算了" | ❌ 跳过 audit = 没产出审计报告 = `docs/audit/{version}/` 目录空 = 后续 Sprint 启动时拿不到基线 |
| "下次再跑也来得及，提示用户 `--audit-only` 即可" | ❌ 没有 `--audit-only` 这个旗标存在；这是 Agent 编造的；用户**只能**通过重跑完整 `/version` 来补审计 <!-- flag-check: ignore --> |
| "执行时间太长，用户在等" | ❌ Agent 调用本身是异步等待 → 主对话**不阻塞**；返回时间通常 < 1 min（4 类产物扫读 + 报告输出）|

**执行检查清单**（命令端进入 Step 2.4.7 之前的最后一道自检 — 必须按顺序口头/书面回答）：
1. ❓ 用户在 `/version` 调用时传了 `--skip-audit` 吗？
   - 是 → 跳过 Step 2.4.7，标"⚠️ 已跳过审计（用户显式 --skip-audit）"
   - 否 → 继续 2
2. ❓ 现在要不要跑 Step 2.4.7 独立子 Agent 审计？
   - **必须答"要"**；如果脑中冒出"为节省上下文跳过"等任何理由，立刻视为违反铁律并强制纠正
3. ❓ 调用 `Agent` 工具的语句已经准备好了吗？
   - 是 → 执行
   - 否 → 立即按上方调用方式段准备并执行

**报告路径约定**：
- fresh 模式：`docs/audit/{version}/version-output-audit-YYYY-MM-DD.md`
- 补充模式：`docs/audit/{version}/version-output-audit-补丁-NN.md`（NN 与本轮 `NN_<业务主题>.md` 增量共用编号）
- 同一天多次审计 → 同文件覆盖；保留 git history 即可追溯历次

