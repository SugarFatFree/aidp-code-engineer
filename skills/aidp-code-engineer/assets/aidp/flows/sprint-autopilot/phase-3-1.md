# sprint-autopilot · Phase 3 详情分片 [1/13]（Phase 3 顶层铁律 + 进入 Phase 3 第一动作硬门）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 1/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：Phase 3 顶层铁律（强制仪式不可精简 / 非法跳过借口 / 报告不可变）+ 进入 Phase 3 的第一动作硬门
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-1.md`。理据见同目录 `rationale.md`。

---

## Phase 3：下版全流程（仅当 TARGET_VERSION 非 null）

> ⛔ **强制仪式不可精简硬门（exit-1 级铁律 — 任何入口模式都不得自行删减）**：下列"强制仪式"在**任何** `ENTRY_MODE`（交互式 `--once` / `full` / `incremental`（bug修复·功能优化增量）/ `test-only`）、任何用户是否在场下**均为强制产出**；**唯一合法跳过 = 命中下表「唯一合法降级条件」**（纯技术性不可用），由 Phase 3.4 step 4「完成核验门」的**确定性外部脚本 `{{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py check`** 逐项 `exit 1` 校验（只认文件产物 + 通知台账，**执行体无法用「已精简 / 交互式」绕过返回码**），未产出且无合法降级即阻断收尾、强制补齐。
>
> | 强制仪式 | 产出位置 | 唯一合法降级条件（命中才可跳/降级）| 降级后动作 |
> |---|---|---|---|
> | **AI执行报告 HTML SPA**（骨架：`data` 计划态 + 结果态 + 注册 index.html/plan.html 两页）| Phase 3.1.5 + 3.4 | **无**（autopilot 自有产物，永不可省；缺失 = 回 Phase 3.0 子流程 R 就地补建）| — |
> | **version-auditor 终审**（独立子 Agent 审计八项 A–H，产 `docs/audit/{V}/` 报告）| Phase 3.3 | **无**（`--skip-audit` 仅 `/version` 内部审计开关，**不豁免** autopilot 终审）| — |
> | **里程碑通知**（按 0.1bis「ENTRY_MODE × 应发通知集矩阵」本模式应发的全部节点）| 0.1bis 各节点 | `NOTIFY_ENABLED=0`（`notify.enabled=false` / 未配置任何 `notify.channels` / `--no-notify`）或 `notify.py --auto` 退出码 3 → 全节点静默跳过 | 终端日志标「里程碑通知跳过」|
> | **报告本体落盘**（HTML 落本地 `docs/reports/{V}/`，#3 / #F 通知附仓库相对路径）| Phase 3.4 Step 2 / aiauto-test #F | **无**（本地落盘永不可省）| — |
>
> ⛔ **非法跳过借口（命中即规范违规，执行体严禁据此精简）**：「交互式执行」「省时 / 提速」「避免打扰团队」「重型仪式 / 流程太重」「用户没明说要报告」「已做精简 / 已简化说明」「单次调用不必全套」「测试通过了报告非必需」「缺前置数据 / 缺测试账号」「需要用户确认才能继续测试」——**一律不是合法降级条件**。★ 后两条另有 Phase 0「用例前置资源对账门」（`phase-0-9.md` 0.6bis）作前置：对账已在 Phase 0 一次性问清并落盘，此后再以"缺前置数据/账号"为由暂停 = **直接判违规**；真缺则按对账门的占位口径标 `block` 继续跑完其余用例，**不是**停下来问人。能跳过仪式的**只有**上表「唯一合法降级条件」列的技术性不可用。执行体若输出"已做精简 / 已简化流程"之类说明却拿不出对应的合法降级条件 = **直接判违规**，完成核验门 `exit 1` 阻断收尾、回对应 Phase 强制补齐。
>
> ⛔ **报告不可变铁律（与「强制仪式不可精简硬门」同级 · exit-非零级）**：AI执行报告 / AI测试报告一经 **finalize**（R-4 收尾：`testSummary` 回填真实值 + 报告落盘 + #3/#F 通知已发 + baseline 置 `builds[].ai_report_finalized=true`+`ai_report_finalized_at`）即**冻结不可改**。此后**任何测试结论变化——无论源于代码修复、产品口径澄清、还是用例范围调整——一律铸新 build 跑新一轮，绝不回写旧 build 的 data**。旧 build 是"当时的事实"、新 build 是"现在的事实"，二者并存才有质量趋势与审计价值。**执行体若在已 finalized 的 build 上重新 emit 报告 = 严重违规**。
> - **确定性兜底（三重锁，非仅 prose）**：① `{{AIDP_HOME}}/scripts/emit-report.py` 检测目标 build 已 `ai_report_finalized` → 拒写 `exit 2`（唯一逃生阀 `--force-amend` 仅修笔误 + 追加 `amendments[]` 留痕）；② Phase 3.1.5 复用判定已收紧——`current_build` 已 finalize/收尾 → **强制铸新 build 跑复测**（标「第 N 轮复测（上轮通过率 X%）」，见 3.1.5）；③ `autopilot-ceremony-gate.py --stage final` 校本 build data mtime 不得晚于 `ai_report_finalized_at`（无 `amendments[]` 留痕的二次篡改 = FAIL）。
> - **结论变化的唯一正确路径**：修复 / 澄清 → 铸新 build → 新一轮实测 → 新报告；旧 build 报告原样保留。趋势与"第一轮 vs 第二轮"对比由多 build 并存天然形成。
> - **★ 铸新 build 出复测报告是【自动仪式】、绝不作为问句抛给用户（本次反馈铁律）**：首测、复测都**无条件出报告**——报告产出是 autopilot 强制仪式（同「强制仪式不可精简硬门」），**不是用户决策点**。复测发现旧 build 报告是上一轮（如"当前报告停留在上一轮 76.9%"）时，Phase 3.1.5 R-1 **自动**铸新 build（`ai_report_finalized` → 强制自增）并自动产新报告，**严禁**弹出/输出诸如"**要我重新铸一个 build 出复测报告吗？**""按报告不可变铁律旧 build 不能改，要不要铸 build1002？"这类**询问**——这是把既定的自动仪式误当选择项，答案**恒为是、直接执行**，交互式与 `/loop` 无人值守下**都不问**。用户的决策点只有一个：是否发起本轮 `/sprint-autopilot`（复测）；一旦发起，铸 build + 出报告是其必然产物、无需再问。「报告不可变」解释的是"为什么走新 build"（旧 build 冻结），**不是"要不要走"的开关**。

> ⛔ **必须铸新 build 的触发条件（J1 — 散落各处的判据在此汇总为一张表，Phase 3.1.5 复用判定的单一信源）**：`current_build` 已 finalize 时，**命中下列任一 → 强制铸新 build 跑新一轮**（绝不复用旧 build、绝不回写旧 data）；`current_build` 未 finalize（仍 `running`/`dev_done`）则复用同一 build 续跑、不新铸。
>
> | # | 触发条件 | 典型场景 | 新 build 标注 |
> |---|---|---|---|
> | ① | **代码修复**后复测 | bugfix 提交 / 自动修复轮 / 人工修复后 | `retest_of` + `retest_round` |
> | ② | **环境修复**后复测 | 上轮因部署未就绪 / 服务未起 而大面积 block，环境修好 | 同上 |
> | ③ | **前置数据恢复**后复测 | 上轮因前置数据缺失 block，数据补齐 | 同上 |
> | ④ | **用例范围调整** | 新增/删除用例、用例口径修订 | 同上 + 报告注明范围变更 |
> | ⑤ | **产品口径澄清** | `pending_clarifications` 被用户确认后 | 同上 |
> | ⑥ | **账号切换后重测**（G1 关联） | 上轮账号失效大面积 block、换有效账号 | 同上 |
>
> 判据一句话：**"上一轮的结论已 finalize 冻结，而现在有任何会改变结论的变化（代码/环境/数据/用例/口径/账号）" → 必铸新 build**。未 finalize 的活动 build 直接续跑。
>
> ⛔ **每个 build 必配套【AI执行报告 + AI测试报告】(J2)**：**任何** build（首测 / 复测 / 环境修复重测）都必须产**两份**报告——**AI执行报告**（autopilot 自产，骨架 Phase 3.1.5 + finalize Phase 3.4/R-4）**+ AI测试报告**（有浏览器测试时由测试链路产；纯静态 `mode=none` 时 AI测试报告以"静态自测、无浏览器测试"结论产）。**⛔ 复测轮绝不允许"只产 AI测试报告、漏 AI执行报告"**（收尾门 `autopilot-ceremony-gate.py` 对每个 build 都校 AI执行报告 SPA 存在——漏产即 `exit 1`）；反之纯静态轮也不得漏 AI执行报告。这堵死"复测只补测试报告卡收尾门、AI执行报告靠事后推断补产"的实跑踩坑。

