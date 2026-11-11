# sprint-autopilot · Phase 0 详情分片 [9/11]（0.6bis 用例前置资源对账门 + 0.7 就绪完整性收口门）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 9/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.6bis（用例前置资源对账门）+ 0.7（AI 自动化开发测试就绪完整性收口门）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **理据**：见同目录 `rationale.md`。

---

### 0.6bis ★ 用例前置资源对账门（把"缺账号/缺前置数据"从借口变成 Phase 0 的一次性事实）

> 0.6 收的是 **baseline 配置字段**，批 6 又把**测试账号**划给 `/sprint-aiauto-test`——于是**用例册声明的前置账号/数据**在 Phase 0 无人负责，成了半路暂停的现成借口。本门补这段真空（理据 + 下游实证见 `rationale.md`「0.6bis 前置资源对账」）。判据确定性：上游 `dev-manual-testcase` 的标准占位符 `{待用户填写: <字段中文名>}` 逐个可数，不做模糊解析。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"   # 取 TARGET_VERSION
python3 {{AIDP_HOME}}/scripts/check_testdata_prereq.py --version "$TARGET_VERSION" --record
python3 {{AIDP_HOME}}/scripts/check_env_archive.py --version "$TARGET_VERSION"   # 约定 38 反向对账
```

- **反向对账 exit 1**（正文已写环境 / 账号、权威文件里没有）→ 按约定 38 补录进 `01_测试环境与账号.md`（prod / UAT 存凭据文件）后复跑，不弹窗问人；地址或账号来源不明、判不准环境的，无人值守下留 WARN 进 0.7（细则 38.9）。

- **`no-casebook`（exit 0）** → 用例册由 `/version` Step 2.4.3.5 才生成，**不是缺陷**：放行，由 **Phase 3.1.5 补账**（`phase-3-4.md`）。
- **`reconciled`（exit 0）** → 通过，进 0.7。
- **`gaps`（exit 1）** → 分流（与 0.6 同构）：**交互式** 属「Phase 0 必问白名单」，现在一次性 `AskUserQuestion` 问清全部缺口 → 写回 `docs/testing/{V}/研发自测/01_测试环境与账号.md`（约定 38 机器消费权威）+ 同步 `01_研发自测方案.md` §3 → commit → 复跑本门；**`/loop` 无人值守** 不弹窗，留占位 + WARN + 里程碑通知提一句，进 0.7。
- ⛔⛔ **本门跑过之后「缺前置数据/缺测试账号」永久不再是暂停理由**（已进 `phase-3-1.md` 非法跳过借口清单）：真缺时**该用例标 `block` + 写明缺什么、继续跑完其余用例**（同 `dev-manual-testcase`「前置不满足记 block、不得换变体凑 pass」），**不是**停下来问人。凭据仍归 `/sprint-aiauto-test` Phase 0.4 收（本门只对账、不收凭据，不越批 6 边界）。

---

### 0.7 ★ AI 自动化开发测试流程就绪完整性总表（Phase 0 收口门 — 缺失即提示补充）

> ★ **核心要求**：autopilot 是开发+测试全链路的**前置门**——**在最开始（Phase 0）就把后续 AI 自动化开发测试流程所需的全部工具 / 环境 / 配置一次性检测齐全，任一必需项缺失就提示用户补充，绝不带病进 Phase 2/3**。本表把分散在 0.1/0.5/0.5.5/0.6 的检查**汇成一张收口清单**（各项检测逻辑仍以"检测位置"列引用的单一信源为准，本表不复写检测法），逐项过一遍后才进 Phase 1。

| 类别 | 就绪项 | 必需性 | 检测位置（单一信源）| 缺失动作 |
|------|-------|--------|------------------|---------|
| 工具 | git 仓库 + 可拉码 | 仅 `vcs_mode=git` 必需 | 0.1 拉码 | `vcs_mode=none` → Git 拉码节点记 `skipped/unsupported:vcs-disabled`，继续本地开发；不得报错退出 |
| 工具 | 里程碑通知渠道（`memory/aidp-config.yaml` 的 `notify` 段）| 可降级 | 0.0 Step 1-2 | 未配置渠道 → `NOTIFY_ENABLED=0` 静默跳过播报（不阻塞、不弹窗）|
| 工具 | **chrome-devtools-mcp（npm 全局包）** | **chrome-mcp 时必需** | **0.5.5 安装预检** | 未装 → **就地打印安装命令**（`npm i chrome-devtools-mcp@latest -g`；远程再 `claude mcp add … --scope project`）让用户挂测试 loop 前装好 |
| 环境 | chrome 连接（本机 CLI / 远程 `.mcp.json`）| chrome-mcp 时必需 | 0.0 Step 5 + 0.5.5 | 远程缺 IP → 收集写 `.mcp.json`；`/loop` 中仍缺 → 留给 `/sprint-aiauto-test` 收集 |
| 环境 | 测试环境访问 URL | chrome-mcp 时必需 | 0.5.5 | **交互式**缺 → AskUserQuestion 收集写回测试方案；**`/loop` 无人值守**缺 → 不弹窗，标 `{待用户填写}` 延后交测试链路（见 0.5.5 第 4 点）|
| 环境 | 部署环境（mode + 启动命令/URL/等待时长）| 必需（除 mode=none）| 0.5/0.6（批 2-4）| **交互式**缺 → AskUserQuestion 一次性收集写回 PRD；**`/loop` 无人值守**缺 → 自动 `deployment.mode=none`（纯开发、跳过部署+实测）+ WARN + 里程碑通知提示，绝不猜 URL |
| 环境 | CICD 流水线 + 就绪探针（`cloud_deploy_trigger=cicd-provider` 时）| 该 trigger 时必需 | 0.5/0.6（批 4d）+ `memory/aidp-config.yaml` 的 `cicd` 段 | 流水线映射未配 / 提供方 CLI·凭据不可用（`cicd_watch.py` 退出码 3）→ 提示配置 `cicd.provider` / `cicd.pipelines` 并按提供方完成登录或设置令牌环境变量；探针 URL 缺 → **交互式**：AskUserQuestion 收集；**`/loop` 无人值守**：⛔ 不弹窗（无人可答＝整 tick 挂到 `tick_max` 超时），标 `{待用户填写}` + WARN + 里程碑通知提示，本轮按「探针不可用」记部署终态 `unknown:probe-url-missing` 继续（见约定 31.5 + Phase 3.2.1）|
| 配置 | PRD `autopilot_decisions` 决策字段 | 必需 | 0.6 | **交互式**缺 → AskUserQuestion 分批收集 + 写回 + commit；**`/loop` 无人值守**缺 → 套「无人值守保守默认表」自动填 + WARN + 里程碑通知提示（不弹窗）；`--strict-prd` 强制退出 |
| 配置 | 测试账号密码 | chrome-mcp 时必需 | 0.5.5 → 委派 `/sprint-aiauto-test` Phase 0.4 | 缺 → 收集到 `研发自测/01_测试环境与账号.md` / credentials |
| 自动判定 + 必问白名单 | `ENTRY_MODE`（full / incremental / test-only）| 必需 | `--skip-dev`→test-only（显式）；full↔incremental 由 3.1.0 PLANNING_DONE 硬判定 | **裁剪只认显式声明**：`--skip-dev` 零交互；**test-intent 关键词无 `--skip-dev` 的裁剪歧义 → 交互式 Phase 0 必问、无人值守保守 full**（P0-0，纠正旧"绝不弹窗自动判 test-only"）|
| 预判 | chrome 驱动前置预判（dev 前就摆出测试能否连/要不要重启）| chrome-mcp 时 | **0.5.5 驱动前置预判** | 五类预判（`check-cli` 矩阵：local-cli-ready / remote-ready / needs-restart-has-fallback / local-chrome-no-cli / blocked-no-fallback）就地打印 + 写 baseline `chrome_preflight`；**只读不连、不阻塞 dev** |
| 自动降级 | 远程 chrome 不可达/需重启 → 本机无头 cli | chrome-mcp 时 | 委派 `/sprint-aiauto-test` 0.1.5 A0/B0 | 非强制远程 + 本机可用 → **自动降级本地无头 cli，零交互**；强制远程 → 交互式 3 分钟重启窗口、超时/无人值守自动切 cli（B0）；**需重启 + 本机无 cli 兜底**（极端）→ 开发照常 + 完成后经里程碑通知（#4）告知原因 + 退出（见 #1d「`chrome_preflight=blocked-no-fallback` 终止处理」）|

**收口判定**：
- **必需项**（含 `test_strategy=chrome-mcp` 时的 chrome 工具/环境/账号）缺失 → **在 Phase 0（现在）提示用户补充**（AskUserQuestion 收集 / 打印安装命令 / 写回配置），收齐才进 Phase 1；`--strict-prd` 下则记入缺失清单退出。
- **可选 / 可降级项**缺失 → 打印一行提示 + 自动降级（不阻塞 7×24 主流程）。
- **`test_strategy=static-only` / 非前端 web** → chrome 相关行整组跳过（仅静态自测，不需要浏览器工具/环境/账号）。
- ★ 与 0.6 铁律一致：所有"可能中途阻塞 Phase 2/3"的就绪项都在此收口，**绝不允许跑到测试链路才发现工具/环境/配置缺失**。
- ⛔ **零交互收口（含自动判定 / 降级项）**：ENTRY_MODE 自动判定（`--skip-dev`/PLANNING_DONE）、远程 chrome 自动降级本地无头也属本收口门覆盖——**`/loop` 无人值守下主流程任何 `AskUserQuestion` = 规范违规**（无人值守恒保守默认全流程）。**交互式（用户在场）例外**：test-intent 裁剪歧义等 Phase 0 必问白名单项**允许且必须在 Phase 0 弹一次**（P0-0，不再"任何情况都不许问"）。

**★ 结构化收尾核验门（钢门，`exit 1` 逐项打勾 —— 把上表从"软清单"升级为"不可绕过"）**：

```bash
# 与 Phase 0 开头「前置硬门」构成两道钢门：本门 = "带缺失绝不放行往下 / 委派"。
# ⚠️ mcp_chrome 只在**远程 chrome 是唯一通路**时才追加。本地 CLI 驱动（默认形态）不需要 .mcp.json，
#    把它无条件加进 REQ 会让本门每 tick 恒 exit 1、Phase 1/2/3 永不进入——
#    `test_strategy=chrome-mcp` 只说明"用 chrome 测"，**不等于"用远程 chrome"**。
#    判据取 Phase 0.5.5 驱动预判写入 baseline 的 chrome_preflight：local-cli-ready = 本机 cli 可跑 → 不要求；
#    其余状态（remote-* / needs-restart-* / blocked-*）才把远程通路视为必需。
CHROME_PREFLIGHT=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get chrome_preflight --default "local-cli-ready")
NEEDS_REMOTE_CHROME=0
# ⛔ 只有**确实要走远程通路**的状态才算必需。此前用「不是这两个就都算必需」的白名单口径，
#   把 `needs-restart-has-fallback` 与 `blocked-no-fallback` 一并划进去 —— 而这两个在
#   phase-0-8 / phase-0-5 的既定策略里都是**降级继续**（前者超时自动切本机无头 cli；
#   后者「开发+部署照常跑完、只是不 invoke /sprint-aiauto-test」）。划错的后果：
#   无人值守下写不了 `.mcp.json`（收集靠 AskUserQuestion）→ 本门每 tick exit 0 →
#   **Phase 1/2/3 永不进入**，`blocked-no-fallback` 尤其自相矛盾（策略要它跑完、门让它进不去）。
case "$CHROME_PREFLIGHT" in
  remote-*) NEEDS_REMOTE_CHROME=1 ;;
  *)        NEEDS_REMOTE_CHROME=0 ;;
esac
REQ=""
test_strategy=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get test_strategy --default "")   # ★ 跨 Bash 块取回，不能当裸 shell 变量用
[ "$test_strategy" = "chrome-mcp" ] && [ "$NEEDS_REMOTE_CHROME" = "1" ] && REQ="mcp_chrome"
# 本门当前唯一的必需项是远程 chrome 通路；REQ 为空 = 无必需项 → 直接放行（其余就绪项均为可降级项，见上表）
if [ -z "$REQ" ]; then
  echo "✅ 0.7 收尾核验门：本轮无必需项（本地 CLI 驱动 / 非 chrome-mcp）→ 放行"
  python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py preflight-gate || exit 1
elif [ -f {{AIDP_HOME}}/scripts/autopilot-preflight.py ]; then
  python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py gate --require "$REQ" || {
    echo "⛔ 收尾核验门未通过 → 回 0.0 对应 Step 就地补做（写 .mcp.json）后复跑本门，通过才进 Phase 1；绝不带缺失进 Phase 1/2/3 或委派 /sprint-aiauto-test"
    # 本 tick 补做并复跑仍失败才执行。统一入口负责记账、冻结幂等和首告警。
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --preflight --command autopilot \
      --reason preflight-gate --why "Phase 0.7 收口门未过（缺 $REQ），无人值守无法收集" \
      --threshold "${PREFLIGHT_THRESHOLD:-3}"
    RC=$?; case "$RC" in 0|3) exit 0;; *) exit "$RC";; esac
  }
  # ★ 门通过 = 本作用域失败已恢复 → 解冻（0.1 只清它自己那 5 个 git 类 reason（外加空 reason 分支），本 reason 留给此处）
  python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py preflight-gate >/dev/null 2>&1 || true
else
  echo "⚠️ preflight 脚本缺失 → 手工逐项核对上表必需项（远程 chrome 时的 .mcp.json），缺则回 0.0 补做；建议重跑 aidp-code-engineer upgrade 补回脚本"
fi
```

- 退出码 1 = 有必需项缺失 → **就地补做 + 复跑本门**，不得带缺失往下（这是与前置硬门"两道钢门"的下游一道）。
- 通知渠道未配置不进本门（播报降级合规）；脏树不进本门（走 0.1 脏树决策门）。

7. 收口通过（前置硬门 + 本收尾核验门均过）→ 进入 Phase 1


