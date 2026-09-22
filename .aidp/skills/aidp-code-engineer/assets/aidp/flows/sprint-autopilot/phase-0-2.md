# sprint-autopilot · Phase 0 详情分片 [2/11]（0.0 Step 2–3 通道就绪打印 / 播报开关落盘）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 2/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.0 Step 2–3（通道就绪打印 + 可选 #0a 通知 / 播报开关汇总落盘）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-2.md`。理据见同目录 `rationale.md`。

---

**Step 2 — 通道就绪打印 + 可选 #0a 通道就绪通知（两命令共享同一份 `notify` 配置）**：

1. **显式打印已配置渠道（绝不静默对外发消息）**：`CH_OK=1` 时终端必打印一行，列出将尝试的渠道类型与顺序（只打印类型与所引用的环境变量名，⛔ 绝不打印 webhook 地址 / 密钥值）：
   ```bash
   python3 {{AIDP_HOME}}/scripts/aidp_config.py get notify.channels
   echo "✅ 里程碑通知渠道就绪（按 notify.channels 顺序尝试，fallback=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get notify.fallback)）；改渠道直接编辑 memory/aidp-config.yaml"
   ```
   `notify` 是**项目级共享**配置（`memory/aidp-config.yaml`，人维护、随仓库提交），不区分成员、不需要逐人确认；密钥只经环境变量引用（`webhook_env` / `secret_env`），故 baseline 与配置文件里都不含任何凭据。
2. **渠道缺失（`CH_OK=0`）→ 交互式与无人值守一律不弹窗**：通知是可选增强，缺失时**当场落盘**降级（见 Step 3 的落盘块），静默跳过本轮全部通知节点。⛔ **不能只置 shell 变量 `NOTIFY_ENABLED=0`**：shell state 不跨 Bash 调用，下游 `tick_flags` 读回的值若与实际不符，收尾门便按「通道可用」索要应发通知台账 → 台账全缺 → 每 tick FAIL → `dev_fail_streak` 累积至冻结。
3. **★ 通道就绪：默认仅终端打印，#0a 通知默认不发（开关 `notify.channel_ready_card`，默认 `false`）**：`CH_OK=1` 后**默认只在终端打印上面一行**——**不每次往群里发"已连接"噪音通知**；**防零播报**已由「终端渠道日志 + 后续真实里程碑通知 #D/#F/#3 自然验证通道」达成。仅当 `memory/aidp-config.yaml` 中 `notify.channel_ready_card: true`（用户显式开启）才发 #0a 轻量确认通知；`notify.py` 返回非 0 → 终端告警，按 Step 3 落盘降级，不阻塞。

> 📌 `/sprint-aiauto-test` 在自己的 Phase 0 读同一份 `notify` 配置；缺失时同样跑本 Step 1+2（保证测试链路独立启动也能播报）。

**Step 3 — 播报开关汇总落盘（`notify` 配置 → `NOTIFY_ENABLED`）**：

**`notify.enabled == true` 且 `notify.channels` 非空** → `NOTIFY_ENABLED=1`；否则 `NOTIFY_ENABLED=0`（降级：静默跳过播报、仅终端日志、不阻塞主流程；熔断/`needs_human` 信号仍照落 baseline，见 0.1bis）。渠道实发失败不在这里判——那由每次 `notify.py --auto` 的退出码决定（见 0.1bis）。

> ⛔⛔ **必须【落盘】、不能只置 shell 变量**：

```bash
# 本块自取配置（分片间 shell 变量不持久，⛔ 不能指望上文的 CH_OK）
N_ENABLED=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get notify.enabled)
N_CHANNELS=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get notify.channels)
if [ "$N_ENABLED" = "true" ] && [ -n "$N_CHANNELS" ] && [ "$N_CHANNELS" != "[]" ]; then
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set notify_enabled true
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py del notify_disabled_reason notify_disabled_at >/dev/null 2>&1 || true
else
  _R=channels-missing; [ "$N_ENABLED" != "true" ] && _R=disabled-in-config
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set notify_enabled false notify_disabled_reason "$_R" notify_disabled_at @now
  echo "ℹ️ 未配置可用通知渠道（$_R）→ 已落盘 notify_enabled=false（本轮跳过播报，不影响主流程）"
fi
```

> ★ 两个留痕字段（`notify_disabled_reason` / `notify_disabled_at`）必带：用户事后补好配置时，下一 tick 本块会重新判定并清掉它们（自动复探），否则无从区分"从没配过"与"配过又关掉"（见 `rationale.md`）。

> **不落盘的后果（实测形态）**：`notify_enabled` 仍是 `true` → 收尾门收到 `--notify 1` → 按 `EXPECT_CARDS`
> 核验应发通知台账 → 台账全缺 → 每 tick FAIL → `dev_fail_streak` 累到阈值写
> `freeze_reason=handoff-exhausted`，而它在 `_HUMAN_ONLY` 里、**探针一律不解冻**。
> 于是冻结原因（"结构性不可自愈"）与真因（通知渠道没配）毫无关系，运维无从据 `freeze_reason` 定位。
> ⚠️ 同款处置在 `phase-0-4.md`（`notify.py` exit 3 = 未配置任何渠道）也要遵守。渠道编排与失败回落见 0.1bis「渠道选择 + 失败回落」。

> 📌 **报告投递**：AI执行报告 + AI测试报告都是离线 HTML SPA，统一落本地 `docs/reports/{version}/…`（随仓库提交）；里程碑通知只附**仓库内相对路径**（或 GitHub 文件链接），故 Phase 0 无报告部署配置需要采集。若团队希望在线浏览，可自行由 CI 把 `docs/reports/` 发布到 GitHub Pages（命令与脚本不负责）。
