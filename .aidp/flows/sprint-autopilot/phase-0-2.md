# sprint-autopilot · Phase 0 详情分片 [2/11]（0.0 Step 2–3 通道就绪打印 / 播报开关落盘）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 2/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.0 Step 2–3（通道就绪打印 + 可选 #0a 通知 / 播报开关汇总落盘）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **理据**：见同目录 `rationale.md`。

---

**Step 2 — 通道就绪打印 + 可选 #0a 通道就绪通知（两命令共享同一份 `notify` 配置）**：

1. **显式打印本地能力诊断（不外发探测消息）**：分片间不沿用 `CH_OK`，重新离线检查；JSON 只输出字段、原因与修复入口，不打印命令完整参数、webhook 地址或密钥值：
   ```bash
   if python3 {{AIDP_HOME}}/scripts/notify.py --check-config --json; then
     CH_OK=1
     echo "通知本地条件就绪；未验证目标参数、鉴权或实际送达。"
   else
     CH_OK=0
     echo "通知本地条件不可用；按上方 repair 修复，主流程继续。"
   fi
   ```
   `notify` 是**项目级共享**配置（`memory/aidp-config.yaml`，人维护、随仓库提交），不区分成员、不需要逐人确认；密钥只经环境变量引用（`webhook_env` / `secret_env`），故 baseline 与配置文件里都不含任何凭据。
2. **本地条件不可用（`CH_OK=0`）→ 交互式与无人值守一律不弹窗**：通知是可选增强，打印明确原因与修复入口，保留用户配置。Step 3 只持久化通知开关，不把缺字段/缺命令写成“已连通”；每个真实通知节点由 `tick_flags` 的 `notify_ready` 和 `notify.py` 统一判可用性、记录失败或不可用。不得把通知不可用升级为测试失败或冻结，也不通过非空 channels 推断迁移完整。
3. **★ 通道就绪：默认仅终端打印，#0a 通知默认不发（开关 `notify.channel_ready_card`，默认 `false`）**：`CH_OK=1` 后**默认只在终端打印上面一行**——**不每次往群里发"已连接"噪音通知**；**防零播报**已由「终端渠道日志 + 后续真实里程碑通知 #D/#F/#3 自然验证通道」达成。仅当 `memory/aidp-config.yaml` 中 `notify.channel_ready_card: true`（用户显式开启）才发 #0a 轻量确认通知；`notify.py` 返回非 0 → 终端告警并按发送结果记未送达，不改用户开关，不阻塞。

> 📌 `/sprint-aiauto-test` 在自己的 Phase 0 读同一份 `notify` 配置；缺失时同样跑本 Step 1+2（保证测试链路独立启动也能播报）。

**Step 3 — 播报开关汇总落盘（`notify` 配置 → `NOTIFY_ENABLED`）**：

**`notify.enabled` 只代表用户通知开关**，保存为 baseline `notify_enabled`；`--no-notify` 可本轮关闭。能力诊断与开关独立：`tick_flags` 读取时还会经 `notify_ready` 把本地不可用的本轮 `NOTIFY_ENABLED` 降为 0，实际里程碑发送结果另记台账。配置非空、通用 schema 齐全、本地可尝试、真实送达不可互相替代；失败不阻塞主流程（见 0.1bis）。

> ⛔⛔ **必须【落盘】、不能只置 shell 变量**：

```bash
# 本块自取配置（分片间 shell 变量不持久，⛔ 不能指望上文的 CH_OK）
N_ENABLED=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get notify.enabled)
if [ "$N_ENABLED" = "true" ]; then
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set notify_enabled true
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py del notify_disabled_reason notify_disabled_at >/dev/null 2>&1 || true
else
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set notify_enabled false notify_disabled_reason disabled-in-config notify_disabled_at @now
  echo "用户通知开关未开启 → 已落盘 notify_enabled=false，不影响主流程。"
fi
```

> ★ 两个留痕字段（`notify_disabled_reason` / `notify_disabled_at`）必带：用户事后补好配置时，下一 tick 本块会重新判定并清掉它们（自动复探），否则无从区分"从没配过"与"配过又关掉"（见 `rationale.md`）。

> 后续每个 Bash 调用仍通过 `tick_flags` 读取本轮有效 `NOTIFY_ENABLED`，不要把持久化的用户开关直接当成能力可用或送达证据。渠道实发失败按 `notify.py` 的 1/3 记未送达/不可用，不让通知故障变成测试冻结；编排与回落见 0.1bis。

> **报告投递**：本地 HTML、下游在线上传、通知送达各自记账。默认仓库相对路径，明确需要仓库访问权限；下游已有上传扩展可保留，结果经 `emit-report.py delivery-repair` 登记，通知经 `--report-kind exec|test` 取 URL 或带原因回落仓库路径。Phase 0 不采集上传凭据、不自动安装服务；不自动 ZIP/附件外发。具体可执行接线见 `{{AIDP_HOME}}/templates/reports/README.md`「只补交付」。
