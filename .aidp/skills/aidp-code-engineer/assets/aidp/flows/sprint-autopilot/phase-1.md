# sprint-autopilot · Phase 1 详情（PRD 变化检测 1.1–1.5）

> 本文件是 `/sprint-autopilot` 命令 **Phase 1（PRD 变化检测 —— 监听核心，仍属准备阶段）** 的完整详细步骤，由命令主体在**进入 Phase 1 时用 `Read` 工具按需加载**。命令主体只保留骨架 + 指针。
>
> ⚠️ **权威性**：进入 Phase 1 后以本文件为准逐项执行。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-1.md`。理据见同目录 `rationale.md`。

---

## Phase 1：PRD 变化检测（监听核心 — 仍属准备阶段）

> ★ Phase 1 仍属「执行前准备」：只做 PRD baseline 监听判定；检测命中后才进入第二部分「执行主流程（Phase 2/3）」（见 1.4）。

### 1.1 Baseline 文件位置（★ 项目级多版本字典）

```
memory/.sprint-autopilot-baseline.json
```

> ★ **baseline 为项目级存储**（命令自动跨多版本工作）；版本状态键为 `versions.{V}`（**项目级共享，不按用户分桶**——本文件团队共享、入库，**绝不记录任何 git 用户名**，autopilot 写哪个版本、aiauto-test 就在同一 `versions.{V}` 读得到，跨用户/跨机也共享一致）。
>
> ★ **本文件入库提交、团队共享**：只存**可共享**内容——版本状态机 + 通知开关 `notify_enabled`，**不含机器/个人特定字段**（远程 Chrome 地址存项目根 `.mcp.json` 的 `chrome-{git_user}`）。敏感的测试账号单独存 gitignored 的 `memory/.sprint-autopilot-credentials.json`。

格式：

```json
{
  "prd_root": "docs/requirements/",
  "schema_version": "2",
  "last_check_at": "2026-06-10T10:30:00+08:00",

  "notify_enabled": true,

  "versions": {
    "V0.1.0": {
      "state": "S3", "last_commit_hash": "abc123...",
      "tracked_files": [{"path": "PRD-用户中心.md", "sha256": "..."}],
      "autopilot_decisions_collected_at": "2026-05-20T10:00:00+08:00",
      "autopilot_decisions_written_to": "docs/requirements/V0.1.0/产品提供/PRD-用户中心.md",
      "internal_released_at": "2026-06-10T12:00:00+08:00"
    },
    "V0.2.0": {
      "state": "S1",
      "last_commit_hash": "def456...",
      "tracked_files": [
        {"path": "PRD-订单中心.md", "sha256": "..."}
      ],
      "autopilot_decisions_collected_at": "2026-06-09T15:00:00+08:00",
      "autopilot_decisions_written_to": "docs/requirements/V0.2.0/产品提供/PRD-订单中心.md",
      "phase_beta_started_at": "2026-06-10T08:00:00+08:00",
      "phase_beta_done_at": "2026-06-10T11:30:00+08:00",
      "last_deployed_at": "2026-06-10T11:31:00+08:00",
      "deployment_mode": "cloud",
      "aiauto_tested_at": null,
      "aiauto_test_report": null,
      "needs_human": false,
      "needs_human_reason": null,
      "needs_human_kind": null,
      "dev_fail_streak": 0,
      "dev_fail_phase": null,
      "dev_fail_freeze_threshold": 3,
      "dev_fail_frozen_at": null,
      "auto_retest_streak": 0,
      "retest_auto_cap": 3,
      "retest_cap_frozen_at": null,
      "retest_frozen_head": null
    }
  },
  "preflight_fail_streak": 0,
  "preflight_frozen_at": null,
  "preflight_fail_reason": null,
  "last_autopilot_head": null
}
```

字段：
- `prd_root`：本 baseline 的 PRD 大目录（默认 `docs/requirements/`）
- `versions.{V}.state`：S0~S4，0.3.3 判定
- `versions.{V}.internal_released_at`：Phase 2 完成时间戳（有值即视为已准发布 → 后续判定为 S3）
- `versions.{V}.phase_beta_done_at` / `last_deployed_at` / `deployment_mode`：sprint-autopilot Phase 3 完成 + 部署完成时写入；**aiauto-test 选版靠 `phase_beta_done_at != null && internal_released_at == null` 定位"当前开发版本"，并读 `last_deployed_at` / `deployment_mode` 做部署探测参考**
- `versions.{V}.aiauto_tested_at` / `aiauto_test_report`：sprint-aiauto-test 跑完后写入；**sprint-autopilot 不写这 2 个字段**（双方协议：autopilot 只写部署侧字段，aiauto-test 只写测试侧字段，避免互踩）
- `versions.{V}.build_seq` / `current_build` / `builds[]`：build 号自增计数器（默认 1000）/ 当前 build `{V}_build{N}`（aiauto-test 据此归属测试结果）/ build 数组。**每条 build 的完整字段清单与各自的写入方 / 读取方见 `rationale.md`「builds[] 字段表」**（本行只留定位，字段语义与写入契约以那张表为单一信源）。
- `versions.{V}.pending_clarifications[]`：★ 测试发现的**需人工确认类**问题（语义/范围）——`{question, affected_cases[], interim_verdict, raised_build, at}`。测试链路 CONVERGED=0 分流时，可自动修复类走自动 bugfix 复测、**需人工确认类记入本数组、不阻塞本轮 finalize**（对应用例记 BLOCK/待确认，#F 通知列出）；用户确认后由 `/sprint-autopilot --once` 铸新 build 复测，严禁回头改旧 build（详见 aiauto-test §3.4 CONVERGED=0 分流 + 报告不可变铁律）
- **★ 版本级熔断字段**（0.3.4 读跳过；step5 / A0 / D / Phase 2 写）：`needs_human` / `needs_human_reason` / `needs_human_kind` / `aiauto_frozen_at` / `freeze_reason` 五件套。**写入契约（缺一即漏）与各 reason 的解冻路径以 `rationale.md`「冻结分类」表为单一信源**，机器门 = `check_freeze_contract.py`，解冻判定 = `autopilot_unfreeze.py::aiauto_probe`。
- **★ 自动复测上限字段**（自动修复复测闭环 step 1/2/3/3bis 读写）：`auto_retest_streak`（**可重置**：每派一轮自动修复 +1、检测到人工修复即归零；报告标注用的 `builds[].retest_round` **不**重置）/ `retest_auto_cap`（默认 3 = 每个人工介入周期最多 3 轮 build）/ `retest_cap_frozen_at` / `retest_frozen_head`（冻结时 `git rev-parse HEAD`）+ **顶层** `last_autopilot_head`（**写入方** = Phase 3.7 云端就绪探针通过后的 push 收尾步；**⚠️ 不写入的场景** = 未走到该步的一切路径——非云端部署形态、探针未过、纯测试 tick、前置失败早退 ⇒ **该字段在多数部署形态下恒空**，判据侧必须容忍空值、不得单靠它下结论。写入方声明义务见 `invariants.md` IRON-9）。step 3bis 用「当前 HEAD ≠ `retest_frozen_head` **且** ≠ `last_autopilot_head`」双重不等区分"人工新提交"与"autopilot 冻结后自推的提交"，防假解冻；**特例**：`retest-cap` 冻结遇人工新提交或新部署即自动解冻 + `auto_retest_streak` 归零 + 铸新 build 复测。
- **★ 两个 tick 级 streak**：`test_loop_missing_streak`（Phase 3.4 dev 完成 tick 首 ++、Phase 2 0b 每 tick 续 ++，权威累加在 Phase 2；达 `TEST_LOOP_MISSING_THRESHOLD`（默认 3）→ 本 build 实跑静态-only finalize + 置 `needs_human`「测试链路未挂载」止损）/ `prerelease_deploy_block_streak`（Phase 2 写：S2 版本本应部署（`deployment_mode`≠none 或 PRD `mode`≠none）却 `last_deployed_at` 为空的连续 tick 数；达 `PRERELEASE_DEPLOY_BLOCK_THRESHOLD`（默认 3）→ 冻结，拒绝把从未就绪/从未实测的部署静默归档为准发布；就绪或无需部署即清零）。
- **★ 顶层前置熔断字段（Phase 0.1 前置失败专用，无版本上下文）**：`preflight_fail_streak`（前置失败连续轮次）/ `preflight_frozen_at`（达阈冻结时刻）/ `preflight_fail_reason`（如 `git-pull-conflict` / `detached-head`）。补 `dev_fail_streak` 在"TARGET_VERSION 尚未解析"阶段的盲区，防 `/loop` 每 tick 刷 #4；前置动作成功一次自动清零，或人工 `--reset-baseline`
- **远程 Chrome 地址**（不在 baseline）：存项目根 `.mcp.json` 的 `chrome-{git_user}.args[--browser-url]`（按 git 用户名分键、入库共享）；`--reset-chrome-ip` = 删该条目重收
- `aiauto_test_heartbeat_at`（顶层，测试链路写）：`/sprint-aiauto-test` 每 tick 起始（迁移后、任何 early-exit 之前）写 = 该 tick 时刻，表征"第二条 `/loop 5m /sprint-aiauto-test --unattended` 存活"（与被测版本无关）；autopilot Phase 3.4 ③ 读它（近 `AIAUTO_TEST_HEARTBEAT_TTL_MIN` 分钟（默认 30，> 测试 loop 周期）内有更新即判活跃），区分"loop 已挂但本 build 尚未出报告"与"loop 未挂载"，免误冻结
- `notify_enabled`（顶层）：里程碑通知开关（派生自 `memory/aidp-config.yaml` 的 `notify.enabled` 且 `notify.channels` 非空，`--no-notify` 可本轮关闭）；两命令共享。渠道地址/密钥不入 baseline（只经 `notify.channels` 引用环境变量）。报告 HTML 只落本地 `docs/reports/{V}/`，通知里的报告链接为仓库相对路径

### 1.2 变化检测逻辑（按版本 per-key 检测）

执行以下 Bash 对 `TARGET_VERSION` 单独检测（**唯一信源是 git + 文件 sha**）：

```bash
PRD_ROOT="${1:-docs/requirements/}"
# ★ 本围栏是 phase-1.md 里**唯一没有 eval --shell 的那个** —— 补上，⛔ 别再写占位符字面量：
#   原样执行会把 `<Phase 0.3.4 识别的 TARGET_VERSION>` 当成版本号去拼路径，PRD_DIR 必不存在
#   → autopilot-prd-watch 返回 should_run=0 → **fail-open 成「PRD 无变化 → 退出」**；
#   而 `--heartbeat` 还会把这个占位串写成 baseline 里的垃圾版本节点。语法合法、零报错。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
: "${TARGET_VERSION:?Phase 0.3.4 尚未落盘 target_version，拒绝按占位符继续}"
PRD_DIR="$PRD_ROOT/$TARGET_VERSION/产品提供/"
BASELINE_FILE="memory/.sprint-autopilot-baseline.json"

# ★ 变化检测内核 = .aidp/scripts/autopilot-prd-watch.py（单一信源，命令端不自行拼哈希比对）
#   判定顺序：无 PRD 文件 → skip(no-prd-files)｜无 baseline 记录 → run(no-baseline)｜
#             last_commit_hash 变了 → run(new-commit)｜tracked_files 归一后不等 → run(uncommitted-change)｜否则 skip(no-change)。
#   ⚠️ 判据两侧必须**同构**后比对（都归一到 [{"path","sha256"}] 排序列表）——脚本已保证；
#      绝不要用"`sha256sum` 文本行的哈希 vs `jq … | tostring` JSON 串的哈希"这种不可比写法（理据见 rationale.md）。
#   --heartbeat：无论是否命中都写顶层 autopilot_loop_heartbeat_at，供运维区分「loop 存活无变化」与「loop 掉了」
#                （与测试链路的 aiauto_test_heartbeat_at 对称）。
eval "$(python3 .aidp/scripts/autopilot-prd-watch.py --version "$TARGET_VERSION" --heartbeat --shell)"
# → 导出 SHOULD_RUN / TRIGGER_REASON / PRD_DIR / PRD_REASON_CODE

# ★ PRE_RELEASE_VERSION 不通过 PRD 变化触发，而是通过 Phase 0.3.3 的"S2 状态"识别
# 因此 SHOULD_RUN 仅控制 Phase 3；Phase 2 独立判定（PRE_RELEASE_VERSION 非 null 即跑）
```

### 1.3 四种触发模式 + 上下文感知

**用户调用上下文（复用 Phase 0.0.0 已派生的 `IS_LOOP_CONTEXT`，不重复探测）**：`IS_LOOP_CONTEXT` 已在 Phase 0.0.0 由 `/loop` 上下文信号就地派生（探测法单一信源见 0.0.0），本节直接沿用：

- `IS_LOOP_CONTEXT=1` → 视为周期性唤起（与 `--no-loop` 等效行为）
- `IS_LOOP_CONTEXT=0` → 视为用户手动调用

| 模式判定优先级 | 行为 |
|--------|------|
| `--once` flag | 跳过 1.2，强制 `SHOULD_RUN=1` → 进执行主流程（Phase 2/3） → 退出 |
| `--watch` flag | Bash 轮询循环（≤ 50 分钟）：每 `--watch-interval` 秒跑 1.2，命中即 break 进执行主流程（Phase 2/3）；50 分钟无变化退出 |
| `--no-loop` flag OR `IS_LOOP_CONTEXT=1` | 执行 1.2 一次：`SHOULD_RUN=1` → 进执行主流程（Phase 2/3）；`SHOULD_RUN=0` **且 `PRE_RELEASE_VERSION` 为 null** → 立即退出；**`SHOULD_RUN=0` 但 `PRE_RELEASE_VERSION` 非 null → 仍进执行主流程**（只跑 Phase 2 上版准发布、跳过 Phase 3）—— 与 1.2 注释「Phase 2 独立判定、`PRE_RELEASE_VERSION` 非 null 即跑」及 0.3.5 决策矩阵对齐 |
| **`LOOP_UNATTENDED=1`（含裸 `--unattended`，无 `/loop`、无 `--once`）★** | **等同 `--no-loop` 行**：执行 1.2 一次并按 `SHOULD_RUN` / `PRE_RELEASE_VERSION` 决定是否进执行主流程。**绝不落到下面的"默认"行**——`--unattended` 的语义就是"没人在场、别打印引导等人"（理据见 `rationale.md`）|
| **默认（无 flag + 无 /loop 上下文 + `LOOP_UNATTENDED=0`）★** | 完成 Phase 0（决策收集/Chrome 检查）→ **输出引导文案提示用户用 `/loop`** → 退出，**不进执行主流程（Phase 2/3）**（详见 1.5 引导文案）|

### 1.3ter ★ 通用 stuck 熔断（先于 1.3bis 跑，**无条件**）

> ⚠️ **`bis`/`ter` 是命名后缀、不表执行顺序**：本步先于 1.3bis 跑（标题已写明）。改名会断全仓对这两个编号的引用，故保留命名、以标题声明顺序为准。

堵「既不失败也不推进」（理据见 `rationale.md`）；判据与冻结契约在脚本内：

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
python3 .aidp/scripts/autopilot_stuck_check.py --version "$TARGET_VERSION"; SC=$?
case "$SC" in   # ⛔ 必须按码分流；禁写 `|| exit 0`（见 rationale）
  1) echo "→ 已冻结（#4 由脚本自己发出）"; exit 0;;
  2) echo "⚠️ 入参/环境错（如本块未代入 TARGET_VERSION）→ 跳过本门继续，不据此退出";;
  3) echo "⛔ stuck 但写盘失败（#4 已发）→ 让位，⛔ 不当已冻结"; exit 0;;
esac
```

### 1.3bis ★ 续跑短路门（先于 1.2 跑，`LOOP_UNATTENDED=1` / `--no-loop` / `/loop` 上下文必查）

**判据**：`run_state.next_phase` 非空且 ≠ `done` → 本 tick 是**上 tick 的续跑**，强制 `SHOULD_RUN=1` 并跳过 1.2 的 PRD 变化检测。（理据见 `rationale.md`「Phase 1 相关根因」。）

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
BE="python3 .aidp/scripts/baseline_edit.py"
RS_PHASE=$($BE --version "$TARGET_VERSION" get run_state.next_phase)
if [ -n "$RS_PHASE" ] && [ "$RS_PHASE" != "done" ]; then
  SHOULD_RUN=1; SKIP_PRD_WATCH=1     # 短路：本轮是上 tick 的续跑，不是"新触发"
  RS_SPRINT=$($BE --version "$TARGET_VERSION" get run_state.next_sprint)
  echo "▶️ run_state 续跑：next_phase=$RS_PHASE next_sprint=${RS_SPRINT:-<无>} → 跳过 1.2 PRD 变化检测，直接进执行主流程"
fi
```

- **短路时不跑 1.4 回写**（`SKIP_PRD_WATCH=1`）：`tracked_files` 首 tick 已写过，续跑途中重复回写会把**期间新到的 PRD 变更吞掉**。
- 游标由各 Phase 出口的 `run-state` 维护；跑到 `next_phase=done` 后本门自动失效，回落 1.2 正常的 PRD 变化检测。

### 1.4 检测命中后

回写 `last_check_at` + `last_trigger_at` + `tracked_files` + `last_commit_hash` → 进执行主流程（Phase 2/3）。**回写与检测必须同源**（否则写进去的结构与下次比对口径不一致，`no-change` 永不成立）：

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
python3 .aidp/scripts/autopilot-prd-watch.py --version "$TARGET_VERSION" --commit
```

⚠️ 不要用裸 `jq … > tmp && mv` 自行拼 `tracked_files`——本脚本内部走 `baseline_edit.py` 的同一把 flock，与测试链路的并发写互斥。

### 1.5 用户直接调用的退出引导（默认模式）

⛔ **退出前先跑收尾门，不得只手写打印**（invariants ③细则）：

```bash
# ⛔ --version 是必填（gate 的 argparse required=True）：漏了它整条命令 exit 2、
#    IRON-4 ③ 的「未进流水线必须结构级打印」在唯一落点上一次都没执行过。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell)"
python3 .aidp/scripts/autopilot-ceremony-gate.py check --version "${TARGET_VERSION:?}" \
  --no-pipeline-reason "配置向导态：未进入执行主流程，本轮无 build 可收尾"
```

跑完再输出（**不进入 Phase 2/3**）：

```
✅ /sprint-autopilot 配置就绪

Phase 0 检查结果：
  ✅ 里程碑通知渠道：{已配置 N 个 | 未配置（本轮静默跳过播报）}
  ✅ PRD 目录：docs/requirements/V0.1.0/产品提供/（{N} 份 .md）
  ✅ autopilot_decisions：决策字段齐全（{首次收集已写回 PRD + commit | 已存在}）
  ✅ git status 干净 | 分支：feature/autopilot-V0.1.0
  ✅ baseline 文件：memory/.sprint-autopilot-baseline.json

ℹ️ 本次为「直接调用 = 配置向导」，未进入开发流水线（Phase 2/3）→ 本轮不产生 build 号 / AI 执行报告 / AI 测试报告 / 里程碑通知。
   （若是要执行某版本的开发：用 /sprint-autopilot --target <版本> --once，或交互式明确"执行 <版本> 的开发并测试"。）

🚀 现在请用 /loop 启动 7×24 守护（★ 必须并行挂【两条】，缺一条则流水线断链）：

    /loop 10m /sprint-autopilot --unattended     # 开发链路：PRD → 规划 → 开发 → 部署
    /loop 5m  /sprint-aiauto-test --unattended   # 测试链路：探测部署 → 浏览器仿真测试 → 报告
    （★ 两条都必须带 --unattended：首个 tick 持久化标志尚未落盘，不带会被判交互式而挂起等人）

（autopilot 每 10 分钟检查 PRD 变化；aiauto-test 每 5 分钟检查是否有新部署）
⚠️ 只挂 autopilot 不挂 aiauto-test → 部署完成后 AI 测试 / 测试报告不会自动触发（浏览器实测 + AI测试报告 + #F 通知全部落空）。

📌 其他用法：
  立即跑一次：  /sprint-autopilot --once
  仅看不跑：    /sprint-autopilot --no-loop（已是 baseline 检查模式）
  跳过开发：    /sprint-autopilot --skip-dev（代码已就绪，只部署 + 测）
  跳过部署：    /sprint-autopilot --skip-deploy（仅开发 + 静态自测）
  查看/停止：   在 Claude Code 用 /loops 看所有 loop 状态，或终止对应 loop / 会话
```

**配置已就绪时**（baseline 含 `autopilot_decisions_collected_at`）：同样版式但只留首行（带上次配置时间）+ 两条 loop + 「立即跑一次 `--once`」，省略 Phase 0 逐项与「其他用法」。

---

