# Hooks 使用说明

## 文件说明

| 文件 | 说明 |
|------|------|
| `autopilot-stop-guard.py` | **Stop Hook**，autopilot 执行态下「收尾门没过不许结束」的结构级兜底（`exit 2` 阻止结束、迫使补产）|

---

## autopilot 收尾门 Stop Hook（`autopilot-stop-guard.py`）

把 `/sprint-autopilot`「命令收尾硬门」从「执行体自律」提为结构级——Agent 试图结束轮次时触发，检测到「autopilot 正处执行态且收尾门 `exit 1`（仪式产物缺失）」→ `exit 2` 阻止结束、迫使继续补产（build / AI执行报告 / 里程碑通知 / 委派测试）。

**作用域：只拦「本会话 / 本进程正在执行 `/sprint-autopilot` tick」的轮次**。判据（任一）：
- 环境变量 `AIDP_TICK_COMMAND=sprint-autopilot`（`agent_loop.sh` / `aidp_scheduler.py` 调度时注入）；
- Stop 输入的 transcript 中最后一条用户输入是 `sprint-autopilot` 命令调用（Claude Code / DeepSeek Harness 为 `/sprint-autopilot`，Codex 为 `$sprint-autopilot`，含 `/loop … /sprint-autopilot`）。

测试链路（`AIDP_TICK_COMMAND=sprint-aiauto-test`）与同一项目里人的普通对话一律放行。

**⛔ 安全第一（本 hook 全局每轮触发，多重 fail-open 保证绝不误 wedge 正常对话）**：
1. **逃生舱**：`touch memory/.autopilot-stop-guard-off` → 立即放行（临时禁用，优先级最高）。
2. **配置开关**：`memory/aidp-config.yaml` 的 `stop_guard.enabled: false` → 放行。
3. **无待收口流水线放行**：非 autopilot tick 轮次 / baseline 缺失 / run_state 无活跃 phase / 有唤醒源且只是让位下一 tick（`next_sprint` 未跑完或 `next_phase` 为 `3.2.1-*` 跨 tick 等待游标）→ 不干预。
4. **判不出 version/build、脚本缺失、任何异常** → 放行（永不因自身故障 wedge）。
5. **熔断上限**：同一 build 连续阻止达 3 次仍未过 → fail-open 放行 + 告警交人工（防无限 wedge）。

只有【全部确定信号齐备 + 收尾门确定 `exit 1` + 未达熔断上限】才 `exit 2`。计数文件 `memory/.aidp/stop-guard-count`（收尾门通过即清）。

**项目根目录解析**（兼容多宿主）：`CLAUDE_PROJECT_DIR` → `CODEX_PROJECT_DIR` / `DSH_PROJECT_DIR`（若宿主注入）→ `git rev-parse --show-toplevel` → 当前工作目录。

---

## 环境要求

- Python ≥ 3.9（标准库，无需安装额外依赖）。模板仓库 `.aidp` 中的 hooks 仅作维护源；下游脚本位于当前 Agent 的 `{{AIDP_HOME}}/hooks/`。无 Git 时使用宿主项目根或当前工作目录回退，不能把 Git 步骤标成通过。

---

## 多 Agent 接线

> ✅ **下游项目无需手动配置**：接线由 `aidp-code-engineer` 脚手架在 **init / migrate / upgrade** 时自动完成，日常也可用 `python3 {{AIDP_HOME}}/scripts/agent_sync.py` 按当前启用的 Agent 幂等补齐——脚本本体只有 `{{AIDP_HOME}}/hooks/` 这一份，各宿主的配置文件只写「Stop 事件 → 调这个脚本」，保留你已有的其它 hook / 配置。手工配置仅用于排查。

| Agent | 配置文件 | 接线方式 |
|------|---------|---------|
| **Claude Code** | `.claude/settings.json`（项目级共享，随 git 提交）| `hooks.Stop` 挂 `python3 {{AIDP_HOME}}/hooks/autopilot-stop-guard.py` |
| **Codex** | `.codex/hooks.json` | Stop 事件挂同一命令（带 `--agent codex`）；须在 `.codex/config.toml` 中开启 `[features] codex_hooks = true`，且项目需被 Codex 信任（trust）才会加载项目级 hooks |
| **DeepSeek Harness** | `.dsh/hooks.json` | Claude Code 格式，Stop 事件挂同一命令（带 `--agent dsh`），由 DeepSeek Harness 的 hooks 插件加载（加载方式以所用版本官方文档为准） |

Claude Code 配置示例（`.claude/settings.json`，已有内容时合并 `hooks` 字段）：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 {{AIDP_HOME}}/hooks/autopilot-stop-guard.py" }
        ]
      }
    ]
  }
}
```

Codex 配置示例（`.codex/hooks.json`）：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 {{AIDP_HOME}}/hooks/autopilot-stop-guard.py --agent codex" }
        ]
      }
    ]
  }
}
```

```toml
# .codex/config.toml
[features]
codex_hooks = true
```

> 命令使用相对路径，须以**项目根目录**为工作目录启动 Agent 会话；宿主未注入项目目录变量时，脚本会回落到 git 根解析。

---

## ⛔ 维护边界（约定 16）

- hook 由脚手架下发并自动接线，下游无需手工配置；改动请在模板项目本体修改后镜像进脚手架。
- 本文件是**脚手架契约文件**，随 `aidp-code-engineer` 下发/升级同步——下游直接手改会在下次升级被覆盖。
