<!-- 二次切分 · phase-0 片6b/9：覆盖 0.2 的两段执行铁律（自愈式交接执行铁律 / #0a·通知配置·报告落点归属分工）-->
# /sprint-aiauto-test · 执行分片 分片 [6b/9]（0.2 的两段执行铁律（自愈式交接执行铁律 / #0a·通知配置·报告落点归属分工））

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。

### 0.2（续）执行铁律（本片覆盖：自愈式交接执行铁律 + #0a / 通知配置 / 报告落点归属分工）

> ⚠️ **本片是 `phase-0-6.md` 的后半**：前半（0.2 子步骤 1–4 的 bash 主体，含冻结字段写入契约 / 熔断门 / 2.5.1 交接判定）在 **`phase-0-6.md`**，须先执行完它再读本片。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-6b.md`。

> ⛔ **自愈式交接执行铁律（2.5.1 的 `NEED_HANDOFF=1` 分支 — 必须照做）**：上面 2.5.1 检出「autopilot 驱动但本 build 的执行数据 data/{BUILD}.js 缺失」（`NEED_HANDOFF=1`）时——本轮是「经意图路由直达 aiauto-test、绕过 autopilot 报告流水线」——**绝不在 AI执行报告缺失下继续测**：立即 invoke `/sprint-autopilot --skip-dev [--unattended] [--no-loop] --target $TARGET_VERSION`（**★ 无人值守透传：`LOOP_UNATTENDED=1` 时交接命令恒带 `--unattended`，有唤醒源（`HAS_WAKE_SOURCE=1`）再加 `--no-loop`——漏传则 autopilot 退化为交互式、在 tick 内命中 `AskUserQuestion` 挂死；autopilot 跑完重新 invoke 本命令时按同一规则透传**；autopilot test-only 入口：跑「子流程 R」产出 AI执行报告 + 跑「完成核验门」，**跑完它会重新 invoke `/sprint-aiauto-test` 把齐全报告带回来**）→ 交接后**结束本轮 aiauto-test**（不再往下，避免重复测）。
> - AI执行报告**骨架**由 autopilot 子流程 R **唯一生产**，本命令不产骨架（约定 21 骨架单一信源）；真实 testSummary 的 finalize + #3 里程碑通知由本命令在 #F 后做（Phase 3.7 · R-4）。
> - 交接**非循环**：autopilot「委派前脚本化硬门」保证只有 AI执行报告齐全才会重新委派回本命令，二次进入时 2.5.1 自然通过（`NEED_HANDOFF=0`）；若 autopilot 子流程 R 失败，它自己的硬门会 `exit 1`、不会带缺失委派回来。
> - **★ `/loop` 无人值守下的 tick 时长意识（防测试 loop 被开发子流程长期借用）**：本重委派在 `LOOP_UNATTENDED=1` 下是**一次性交接、非本 tick 必须闭环**——若 autopilot 子流程 R 自身卡住 / 长时间未返回（如其 Phase 3.4 完成核验门反复 FAIL），**由 autopilot 侧熔断兜底**（`dev_fail_streak` / `dev_fail_phase="3.4-ceremony-gate"` 达阈冻结本版，见 autopilot 失败处置 step5），本测试 tick **让位结束、交下次测试 `/loop` 唤起时按 baseline 状态复判**，绝不在测试 tick 内无限同步等待开发子流程。
> - **★ 本地 `handoff_fail_streak` 兜底熔断（不只依赖 autopilot 侧 `dev_fail_streak`，缩短跨命令熔断链）**：
>   **计数时机 = 发起交接那一刻就 +1，不是"二次进入时才 +1"**（⚠️ 后者的递增条件不可达：autopilot 子流程 R 自己 `exit 1` 后**根本不会 invoke 回本命令**，"二次进入"这个事件永远不发生，计数恒 0、熔断永不触发）。落地：
>   ```bash
>   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
>   # 发起交接【之前】先记账（⛔ 记账唯一落点在下方 autopilot_fail_handle.py，本行只读当前值用于日志）
>   N=$(python3 .aidp/scripts/baseline_edit.py --version "$TARGET_VERSION" get handoff_fail_streak --default 0)
>   ```
>   **清零不在本片**：本片只在 `NEED_HANDOFF=1` 时被 Read，而清零要在 `NEED_HANDOFF=0` 的成功分支执行——
>   落点在 `phase-0-6.md` 的「✅ AI执行报告骨架就绪」分支与 `phase-3-3.md` 的「✅ 完成核验」分支，两处均为可执行语句。
>   **连续 ≥3 次交接仍拿不回齐全报告**时本命令**本地**冻结本版——记账/判阈/四件套/#4 一次做完
>   （**替代**上面那次裸 `bump`：⛔ 别两处都记账，否则一轮交接记两次、阈值提前一半到达）：
>   ```bash
>   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
>   python3 .aidp/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
>     --phase 0.6-handoff --reason handoff-exhausted --streak-key handoff_fail_streak \
>     --threshold "${HANDOFF_FAIL_THRESHOLD:-3}" \
>     --why "连续多次交接仍拿不回齐全 AI执行报告"
>   ```
>   达阈（退出码 3）后静默，**不再交接**、后续测试 tick 对本版静默跳过。**Why**：autopilot 子流程 R 若走到某条未递增其 `dev_fail_streak` 的失败路径，纯靠跨命令熔断会令测试 tick 每次都交接→autopilot 无产物返回→再交接地隐性空转；本地计数是独立第二道闸。
> - ⛔ **严禁**：识别到"只跑测试"就手驱浏览器、在 AI执行报告缺失下散落 AI测试报告。

> ★ **#0a / 通知配置 / 报告落点归属（两命令分工写死 —— 杜绝"两边都以为对方做了"的真空）**：
> - **委派路径**（autopilot → 本命令，`REPORT_ENABLED=1`）：通知渠道由人维护的 `memory/aidp-config.yaml` `notify` 段统一提供，本命令**直接继承**——**不发 #0a**（#0a 通道就绪通知默认不发、且本命令早期里程碑是 #D 部署完成通知）。
> - **standalone 路径**（无 autopilot baseline / `--once` / 未挂 autopilot 的独立 `/loop`）：本命令在 **Phase 0.2 子步骤 4** 自读 `notify` 段；未启用或未配置渠道 → 里程碑通知静默跳过，⛔ 不弹窗收集。
> - 报告落点两路径一致：恒为本地 `docs/reports/{V}/`，无需询问；通知中的报告链接用仓库相对路径。
